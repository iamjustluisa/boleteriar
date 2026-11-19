"""Genera los manifiestos de Kubernetes de los microservicios (python k8s/generar.py)."""
from pathlib import Path

SERVICIOS = ["usuarios", "acceso", "escenarios", "eventos", "localidades", "asientos", "disponibilidad", "reservas",
             "compras", "pagos", "boletas", "notificaciones", "auditoria", "analitica"]
AQUI = Path(__file__).parent


def deployment(nombre: str, replicas: int = 1, extra_env: str = "") -> str:
    return f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {nombre}
  labels: {{app.kubernetes.io/name: {nombre}, app.kubernetes.io/part-of: boleteria}}
spec:
  replicas: {replicas}
  selector:
    matchLabels: {{app.kubernetes.io/name: {nombre}}}
  template:
    metadata:
      labels: {{app.kubernetes.io/name: {nombre}, app.kubernetes.io/part-of: boleteria}}
    spec:
      containers:
        - name: {nombre}
          image: boleteria-app:1.0
          imagePullPolicy: IfNotPresent
          env:
            - {{name: SERVICIO, value: {nombre}}}
            - {{name: PORT, value: "8000"}}{extra_env}
          envFrom:
            - configMapRef: {{name: boleteria-config}}
            - secretRef: {{name: boleteria-secretos}}
          ports:
            - {{containerPort: 8000, name: http}}
          readinessProbe:
            httpGet: {{path: {"/api/estado" if nombre == "gateway" else "/health"}, port: http}}
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet: {{path: /health, port: http}}
            initialDelaySeconds: 30
            periodSeconds: 20
          resources:
            requests: {{cpu: 50m, memory: 96Mi}}
            limits: {{cpu: 500m, memory: 256Mi}}
---
apiVersion: v1
kind: Service
metadata:
  name: {nombre}
  labels: {{app.kubernetes.io/name: {nombre}, app.kubernetes.io/part-of: boleteria}}
spec:
  selector: {{app.kubernetes.io/name: {nombre}}}
  ports:
    - {{name: http, port: 8000, targetPort: http}}
"""


partes = [deployment(s) for s in SERVICIOS]
(AQUI / "microservicios.yaml").write_text("# Generado por k8s/generar.py: un Deployment y un Service por microservicio.\n"
                                         + "---\n".join(partes))
gw = deployment("gateway", 2, "\n            - {name: SEED_AL_INICIAR, value: \"true\"}")
gw += """---
apiVersion: v1
kind: Service
metadata:
  name: gateway-publico
  labels: {app.kubernetes.io/part-of: boleteria}
spec:
  type: NodePort
  selector: {app.kubernetes.io/name: gateway}
  ports:
    - {name: http, port: 80, targetPort: http, nodePort: 30080}
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: gateway
spec:
  scaleTargetRef: {apiVersion: apps/v1, kind: Deployment, name: gateway}
  minReplicas: 2
  maxReplicas: 5
  metrics:
    - type: Resource
      resource:
        name: cpu
        target: {type: Utilization, averageUtilization: 70}
"""
(AQUI / "gateway.yaml").write_text("# Generado por k8s/generar.py: API Gateway (2 réplicas), acceso por NodePort 30080 y autoescalado.\n" + gw)
print("ok")
