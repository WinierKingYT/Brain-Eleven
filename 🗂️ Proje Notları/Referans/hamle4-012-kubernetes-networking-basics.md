---
type: decision
title: Kubernetes Networking - Pod Communication Essentials
category: Security & DevOps
status: active
created: 2026-08-27
source: kelseyhightower/kubernetes-the-hard-way (Hamle 4)
tags: [kubernetes, networking, pods, services, devops]
---

# K8s Networking Fundamentals

**Pattern:** Pod-to-Pod and Service Discovery

## Pod Networking

```
Each pod gets unique IP (172.17.0.x)
Pods on same node: communicate via bridge
Pods on different nodes: overlay network (Flannel/Calico/Weave)

Pod A (10.0.0.5) ──→ Pod B (10.0.0.6)
  └─ Service DNS: my-service.default.svc.cluster.local
     └─ Points to ClusterIP (internal LB)
```

## Service Types

| Type | Purpose | Internal | External |
|------|---------|----------|----------|
| ClusterIP | Internal only | ✓ | ✗ |
| NodePort | External access | ✓ | ✓ (port 30000+) |
| LoadBalancer | Cloud LB | ✓ | ✓ |
| ExternalName | External service | ✗ | ✓ |

## Pod Communication Patterns

```
Same namespace:
  pod A → my-service → pod B

Different namespace:
  pod A → my-service.other-ns.svc.cluster.local → pod B

External service:
  pod A → external-api.com (via DNS)
```

## Network Policy (Security)

```
Deny all:
  apiVersion: networking.k8s.io/v1
  kind: NetworkPolicy
  metadata:
    name: deny-all
  spec:
    podSelector: {}
    policyTypes:
    - Ingress

Allow specific:
  spec:
    ingress:
    - from:
      - podSelector:
          matchLabels:
            app: frontend
```

---

**Bağlantılar:** [[hamle4-010-sre-sli-slo-sla]]
