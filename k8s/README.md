# Despliegue en Kubernetes (Sprint 6)

Manifiestos para un clúster local (minikube, kind, k3s, Docker Desktop) o en la nube.

| Archivo | Contenido |
|---|---|
| `namespace.yaml` | Espacio de nombres `boleteria`. |
| `mysql.yaml` | MySQL 8 como StatefulSet con volumen persistente (5 Gi) y Service interno `mysql`. |
| `microservicios.yaml` | Un Deployment y un Service por microservicio (13 transaccionales + analítica). |
| `gateway.yaml` | API Gateway con 2 réplicas, Service NodePort 30080 y autoescalado (HPA) por CPU. |
| `kustomization.yaml` | Une todo, genera el ConfigMap de configuración y el Secret desde `secretos.env`. |
| `generar.py` | Regenera `microservicios.yaml` y `gateway.yaml`. |

## Pasos

```bash
# 1. Construir la imagen y cargarla en el clúster
docker build -t boleteria-app:1.0 .
minikube image load boleteria-app:1.0        # o: kind load docker-image boleteria-app:1.0

# 2. Secretos (no se suben al repositorio)
cp k8s/secretos.env.example k8s/secretos.env  # y cambia las contraseñas

# 3. Espacio de nombres y scripts SQL de inicialización
kubectl apply -f k8s/namespace.yaml
kubectl -n boleteria create configmap mysql-initdb --from-file=database/

# 4. Desplegar
kubectl apply -k k8s
kubectl -n boleteria get pods -w

# 5. Abrir la aplicación
minikube service -n boleteria gateway-publico   # o http://<IP-del-nodo>:30080
```

El HorizontalPodAutoscaler del gateway necesita `metrics-server` (`minikube addons enable metrics-server`).
