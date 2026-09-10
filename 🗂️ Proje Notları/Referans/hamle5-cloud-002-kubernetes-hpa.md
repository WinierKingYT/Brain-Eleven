---
type: decision
title: Kubernetes Horizontal Pod Autoscaler - Load-Based Scaling
category: Cloud Architecture & DevOps
status: active
created: 2026-08-28
source: kubernetes/kubernetes (Hamle 5)
tags: [kubernetes, autoscaling, hpa, load-balancing, devops]
---

# Kubernetes HorizontalPodAutoscaler

**Pattern:** Automatic Pod Scaling Based on Metrics

## Core Concept

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: app-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: app
  
  minReplicas: 2
  maxReplicas: 20
  
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

## Scaling Behavior

```
Current load: 50%
Target: 70%
Action: Scale DOWN (less capacity needed)

Current load: 90%
Target: 70%
Action: Scale UP (add pods)

Calculation:
  desiredReplicas = ceil(currentReplicas * currentMetric / targetMetric)
  
  Example:
    currentReplicas = 3
    currentCPU = 90%
    targetCPU = 70%
    desiredReplicas = ceil(3 * 90 / 70) = ceil(3.86) = 4 pods
```

## CPU-Based Scaling

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: cpu-scaler
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  
  minReplicas: 2
  maxReplicas: 50
  
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300  # Wait 5 min before scaling down
      policies:
      - type: Percent
        value: 50                       # Remove max 50% of pods
        periodSeconds: 60
    
    scaleUp:
      stabilizationWindowSeconds: 0    # Scale up immediately
      policies:
      - type: Percent
        value: 100                      # Double pods
        periodSeconds: 60
```

## Custom Metrics

```yaml
# Scale based on application metrics (not just CPU/memory)
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: custom-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: worker
  
  minReplicas: 1
  maxReplicas: 100
  
  metrics:
  - type: Pods
    pods:
      metric:
        name: requests_per_second
      target:
        type: AverageValue
        averageValue: "1000"  # 1000 req/sec per pod
```

## Gotchas

```
❌ Too aggressive scaling (flapping)
  Pods scale up → cooled down → scale down → too few → scale up
  Result: Constant churn, wasted resources
  
  ✓ Use stabilizationWindowSeconds (300s = 5 min minimum)
  ✓ Use conservative percentages (50% at a time)

❌ Setting target too high
  If targetCPU = 95%, will only scale when at max capacity
  
  ✓ Set target = 70% (leaves headroom)

❌ No resource requests/limits
  HPA needs baseline to work properly
  
  ✓ Define resources:
    resources:
      requests:
        cpu: 100m
        memory: 128Mi
      limits:
        cpu: 500m
        memory: 512Mi

❌ Not monitoring actual scale events
  Scaling may fail silently (quota limits, node limits)
  
  ✓ Monitor HPA status
    kubectl describe hpa app-hpa
```

## Monitoring

```bash
# Check HPA status
kubectl get hpa

# Watch scaling in action
kubectl get hpa app-hpa --watch

# Detailed status
kubectl describe hpa app-hpa

# Check events
kubectl get events --sort-by='.lastTimestamp'
```

---

**Bağlantılar:** [[hamle5-cloud-003-multi-region-failover]]
