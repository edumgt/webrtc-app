#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

required_envs=(
  AWS_REGION
  EC2_AMI_ID
  EC2_KEY_NAME
  EC2_SECURITY_GROUP_ID
  EC2_SUBNET_ID
  SSH_PRIVATE_KEY_PATH
)

for env_name in "${required_envs[@]}"; do
  if [[ -z "${!env_name:-}" ]]; then
    echo "ERROR: ${env_name} is required."
    exit 1
  fi
done

required_cmds=(aws docker ssh base64)
for cmd in "${required_cmds[@]}"; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "ERROR: '${cmd}' command is required."
    exit 1
  fi
done

if [[ ! -f "${SSH_PRIVATE_KEY_PATH}" ]]; then
  echo "ERROR: SSH private key not found: ${SSH_PRIVATE_KEY_PATH}"
  exit 1
fi

AWS_ARGS=(--region "${AWS_REGION}")
if [[ -n "${AWS_PROFILE:-}" ]]; then
  AWS_ARGS+=(--profile "${AWS_PROFILE}")
fi

aws_cli() {
  aws "${AWS_ARGS[@]}" "$@"
}

EC2_INSTANCE_TYPE="${EC2_INSTANCE_TYPE:-t3.large}"
EC2_ASSOCIATE_PUBLIC_IP="${EC2_ASSOCIATE_PUBLIC_IP:-true}"
EC2_INSTANCE_NAME="${EC2_INSTANCE_NAME:-webrtc-k3s-node}"
SSH_USER="${SSH_USER:-ec2-user}"
K8S_NAMESPACE="${K8S_NAMESPACE:-webrtc}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
ECR_FRONTEND_REPO="${ECR_FRONTEND_REPO:-webrtc-frontend}"
ECR_SIGNALING_REPO="${ECR_SIGNALING_REPO:-webrtc-signaling}"

AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws_cli sts get-caller-identity --query Account --output text)}"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "[1/8] ECR repository 준비"
for repo in "${ECR_FRONTEND_REPO}" "${ECR_SIGNALING_REPO}"; do
  if ! aws_cli ecr describe-repositories --repository-names "${repo}" >/dev/null 2>&1; then
    aws_cli ecr create-repository --repository-name "${repo}" >/dev/null
  fi
done

echo "[2/8] ECR 로그인"
aws_cli ecr get-login-password | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

echo "[3/8] Docker 이미지 빌드/푸시"
FRONTEND_IMAGE="${ECR_REGISTRY}/${ECR_FRONTEND_REPO}:${IMAGE_TAG}"
SIGNALING_IMAGE="${ECR_REGISTRY}/${ECR_SIGNALING_REPO}:${IMAGE_TAG}"

docker build -f "${ROOT_DIR}/Dockerfile.frontend" -t "${FRONTEND_IMAGE}" "${ROOT_DIR}"
docker push "${FRONTEND_IMAGE}"

docker build -f "${ROOT_DIR}/Dockerfile.signaling" -t "${SIGNALING_IMAGE}" "${ROOT_DIR}"
docker push "${SIGNALING_IMAGE}"

echo "[4/8] EC2 생성"
NETWORK_INTERFACE_SPEC="DeviceIndex=0,SubnetId=${EC2_SUBNET_ID},Groups=${EC2_SECURITY_GROUP_ID},AssociatePublicIpAddress=${EC2_ASSOCIATE_PUBLIC_IP}"

run_instances_args=(
  ec2 run-instances
  --image-id "${EC2_AMI_ID}"
  --instance-type "${EC2_INSTANCE_TYPE}"
  --key-name "${EC2_KEY_NAME}"
  --network-interfaces "${NETWORK_INTERFACE_SPEC}"
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${EC2_INSTANCE_NAME}}]"
  --count 1
  --query "Instances[0].InstanceId"
  --output text
)

if [[ -n "${EC2_IAM_INSTANCE_PROFILE_NAME:-}" ]]; then
  run_instances_args+=(--iam-instance-profile "Name=${EC2_IAM_INSTANCE_PROFILE_NAME}")
fi

INSTANCE_ID="$(aws_cli "${run_instances_args[@]}")"
echo "InstanceId: ${INSTANCE_ID}"

aws_cli ec2 wait instance-running --instance-ids "${INSTANCE_ID}"
aws_cli ec2 wait instance-status-ok --instance-ids "${INSTANCE_ID}"

PUBLIC_IP="$(aws_cli ec2 describe-instances --instance-ids "${INSTANCE_ID}" --query "Reservations[0].Instances[0].PublicIpAddress" --output text)"
echo "Public IP: ${PUBLIC_IP}"

SSH_OPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "${SSH_PRIVATE_KEY_PATH}")

echo "[5/8] SSH 준비 대기"
for _ in {1..60}; do
  if ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" "echo ready" >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

echo "[6/8] EC2에 k3s(Kubernetes) 설치"
ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" \
  "curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC='--write-kubeconfig-mode 644' sh -"

echo "[7/8] Kubernetes 리소스 배포"
ECR_PASSWORD="$(aws_cli ecr get-login-password)"
ECR_PASSWORD_B64="$(printf '%s' "${ECR_PASSWORD}" | base64 | tr -d '\n')"
PUBLIC_SIGNAL_URL="${PUBLIC_SIGNAL_URL:-ws://${PUBLIC_IP}:30081}"

ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" \
  "K8S_NAMESPACE='${K8S_NAMESPACE}' ECR_REGISTRY='${ECR_REGISTRY}' ECR_PASSWORD_B64='${ECR_PASSWORD_B64}' FRONTEND_IMAGE='${FRONTEND_IMAGE}' SIGNALING_IMAGE='${SIGNALING_IMAGE}' PUBLIC_SIGNAL_URL='${PUBLIC_SIGNAL_URL}' bash -s" <<'REMOTE'
set -euo pipefail

sudo kubectl create namespace "${K8S_NAMESPACE}" --dry-run=client -o yaml | sudo kubectl apply -f -

ECR_PASSWORD="$(printf '%s' "${ECR_PASSWORD_B64}" | base64 -d)"
AUTH_B64="$(printf 'AWS:%s' "${ECR_PASSWORD}" | base64 | tr -d '\n')"
DOCKER_CONFIG_PATH="$(mktemp)"
cat > "${DOCKER_CONFIG_PATH}" <<JSON
{
  "auths": {
    "${ECR_REGISTRY}": {
      "username": "AWS",
      "password": "${ECR_PASSWORD}",
      "auth": "${AUTH_B64}"
    }
  }
}
JSON
sudo kubectl -n "${K8S_NAMESPACE}" create secret generic ecr-regcred \
  --type=kubernetes.io/dockerconfigjson \
  --from-file=.dockerconfigjson="${DOCKER_CONFIG_PATH}" \
  --dry-run=client -o yaml | sudo kubectl apply -f -
rm -f "${DOCKER_CONFIG_PATH}"

cat <<YAML | sudo kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: webrtc-signaling
  namespace: ${K8S_NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: webrtc-signaling
  template:
    metadata:
      labels:
        app: webrtc-signaling
    spec:
      imagePullSecrets:
        - name: ecr-regcred
      containers:
        - name: signaling
          image: ${SIGNALING_IMAGE}
          imagePullPolicy: Always
          env:
            - name: SIGNAL_HOST
              value: "0.0.0.0"
            - name: SIGNAL_PORT
              value: "3001"
          ports:
            - containerPort: 3001
---
apiVersion: v1
kind: Service
metadata:
  name: webrtc-signaling
  namespace: ${K8S_NAMESPACE}
spec:
  type: NodePort
  selector:
    app: webrtc-signaling
  ports:
    - port: 3001
      targetPort: 3001
      nodePort: 30081
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: webrtc-frontend
  namespace: ${K8S_NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: webrtc-frontend
  template:
    metadata:
      labels:
        app: webrtc-frontend
    spec:
      imagePullSecrets:
        - name: ecr-regcred
      containers:
        - name: frontend
          image: ${FRONTEND_IMAGE}
          imagePullPolicy: Always
          env:
            - name: FRONTEND_HOST
              value: "0.0.0.0"
            - name: FRONTEND_PORT
              value: "80"
            - name: VITE_SIGNAL_URL
              value: "${PUBLIC_SIGNAL_URL}"
          ports:
            - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: webrtc-frontend
  namespace: ${K8S_NAMESPACE}
spec:
  type: NodePort
  selector:
    app: webrtc-frontend
  ports:
    - port: 80
      targetPort: 80
      nodePort: 30080
YAML

sudo kubectl -n "${K8S_NAMESPACE}" rollout status deployment/webrtc-signaling --timeout=300s
sudo kubectl -n "${K8S_NAMESPACE}" rollout status deployment/webrtc-frontend --timeout=300s
sudo kubectl -n "${K8S_NAMESPACE}" get pods -o wide
REMOTE

echo "[8/8] 완료"
echo "Frontend URL: http://${PUBLIC_IP}:30080"
echo "Signaling URL: ${PUBLIC_SIGNAL_URL}"
echo "Instance ID: ${INSTANCE_ID}"
