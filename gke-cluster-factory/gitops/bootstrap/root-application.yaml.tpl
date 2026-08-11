apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: platform-baseline
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: __REPO_URL__
    targetRevision: __REVISION__
    path: gitops/charts/platform-baseline
    helm:
      releaseName: platform-baseline
      parameters:
        - name: gitops.repoURL
          value: __REPO_URL__
        - name: cluster.name
          value: __CLUSTER_NAME__
        - name: access.ownerGroup
          value: __OWNER_GROUP__
        - name: access.team
          value: __TEAM__
        - name: access.platformAdminGroup
          value: __PLATFORM_ADMIN_GROUP__
        - name: access.iamPrincipalType
          value: __IAM_PRINCIPAL_TYPE__
        - name: environment
          value: __ENVIRONMENT__
        - name: workloadExposure
          value: __WORKLOAD_EXPOSURE__
  destination:
    server: https://kubernetes.default.svc
    namespace: platform-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
      allowEmpty: false
    syncOptions:
      - CreateNamespace=true
      - PruneLast=true
      - ServerSideApply=true
    retry:
      limit: 5
      backoff:
        duration: 10s
        factor: 2
        maxDuration: 3m
