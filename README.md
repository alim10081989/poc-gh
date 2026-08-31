# Sample Project — App Build + Docker Image via GitHub Actions → ECR

A minimal, runnable Flask app used to prove out the build pipeline end-to-end
before wiring in Helm/GitOps. No cluster, no Helm — just: test → build image → scan → push.

## Project structure

```
poc-sample/
├── .github/workflows/build.yml   # the CI pipeline
├── app/
│   ├── app.py                    # Flask app: /, /healthz, /readyz
│   ├── requirements.txt          # runtime deps
│   ├── requirements-dev.txt      # + pytest for CI
│   ├── Dockerfile                # multi-stage, non-root, healthcheck
│   ├── .dockerignore
│   └── tests/test_app.py         # unit tests that gate the pipeline
└── aws/
    ├── trust-policy.json         # OIDC trust — who can assume the role
    └── ecr-push-policy.json      # scoped IAM permissions
```

## Run it locally first

```bash
cd app
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/ -v                  # should pass — 3 tests
python app.py                     # visit http://localhost:8080
```

```bash
docker build -t myapp:local .
docker run -p 8080:8080 myapp:local
curl http://localhost:8080/healthz
```

## One-time AWS setup

Run these once per AWS account/repo. Replace `123456789012`, `ap-south-1`, and
`yourorg/poc-sample` with your actual account ID, region, and GitHub repo path.

```bash
# 1. Create the OIDC provider (skip if your account already has one —
#    check first with: aws iam list-open-id-connect-providers)
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1

# 2. Create the IAM role GitHub Actions assumes
aws iam create-role \
  --role-name github-actions-ecr-push \
  --assume-role-policy-document file://aws/trust-policy.json

# 3. Attach scoped ECR permissions
aws iam put-role-policy \
  --role-name github-actions-ecr-push \
  --policy-name ecr-push-scoped \
  --policy-document file://aws/ecr-push-policy.json

# 4. Create the ECR repo — immutable tags + scan on push
aws ecr create-repository \
  --repository-name myapp \
  --image-scanning-configuration scanOnPush=true \
  --image-tag-mutability IMMUTABLE \
  --region ap-south-1
```

## GitHub setup

1. Create a repo, e.g. `yourorg/poc-sample`, push this project to it
2. No secrets to add — OIDC means no `AWS_ACCESS_KEY_ID` in GitHub at all
3. Update these values to match your environment:
   - `aws/trust-policy.json` → the `sub` condition (repo path)
   - `.github/workflows/build.yml` → `AWS_ACCOUNT_ID`, `AWS_REGION`, `ECR_REPOSITORY`
4. Push to a feature branch, open a PR → only `build-test` job runs (tests only)
5. Merge to `main` → both jobs run, image gets built, scanned, and pushed to ECR

## Verify the pushed image

```bash
aws ecr describe-images --repository-name myapp --region ap-south-1
```

You should see a tag like `1.0.3-a1b2c3d` and `latest-dev`.

## Stage 2: Helm chart + GitOps handoff (now included)

```
app/helm/myapp/
├── Chart.yaml           # chart version — bumps independently of the image tag
├── values.yaml           # baseline defaults
├── values-dev.yaml        # per-env overrides
├── values-qa.yaml
├── values-uat.yaml
├── values-prod.yaml
└── templates/
    ├── _helpers.tpl
    ├── deployment.yaml
    ├── service.yaml
    └── hpa.yaml
```

The pipeline now has 4 jobs, each depending on the last:

1. **build-test** — unit tests, computes the image tag
2. **build-push-image** — builds, scans, pushes the image (unchanged from stage 1)
3. **package-push-chart** — lints the chart, packages it with a chart version tied to
   `Chart.yaml` + run number, pushes it to ECR as an OCI artifact under `charts/myapp`.
   `--app-version` is set to the image tag for `helm list` visibility — the chart's
   `values.yaml image.tag` is what actually controls the deployed image.
4. **update-gitops-dev** — checks out the separate `gitops-repo`, bumps
   `envs/dev/myapp/values.yaml` with the new image tag + chart version, commits and
   pushes. This is the only job that touches deploy state — ArgoCD (not this
   pipeline) does the actual cluster sync from there.

### Why chart version and image tag are separate

`Chart.yaml`'s `version` changes only when the templates change (new probe, new
resource limit, new HPA). The image tag changes on every app code merge. Bumping
one doesn't force a bump of the other — you can ship a resource-limit tweak
without rebuilding the app, and ship 10 app releases without ever touching the
chart version.

### Additional one-time setup for stage 2

```bash
# ECR repo for the Helm chart (OCI) — separate from the image repo
aws ecr create-repository \
  --repository-name charts/myapp \
  --image-tag-mutability IMMUTABLE \
  --region ap-south-1
```

The updated `aws/ecr-push-policy.json` now scopes push access to both
`repository/myapp` (image) and `repository/charts/myapp` (chart) — re-apply it:

```bash
aws iam put-role-policy \
  --role-name github-actions-ecr-push \
  --policy-name ecr-push-scoped \
  --policy-document file://aws/ecr-push-policy.json
```

### New GitHub secret required

Job 4 pushes to a **second** repo (`gitops-repo`), which the default
`GITHUB_TOKEN` can't access. Create a fine-grained PAT (or GitHub App
installation token) scoped to **only** `gitops-repo`, contents read/write,
and add it as a repo secret:

```
Settings → Secrets and variables → Actions → New repository secret
Name: GITOPS_REPO_TOKEN
```

Also update `yourorg/gitops-repo` in the workflow to your actual gitops repo
path, and make sure that repo has the folder `envs/dev/myapp/values.yaml`
already committed (even a placeholder) before the first run — `yq -i` edits an
existing file, it doesn't create one from scratch.

## Tear down

Reverses the "One-time AWS setup" and "Additional one-time setup for stage 2"
steps above, in the opposite order (policy/role before the provider, repos
before either). Run only the pieces you actually created — e.g. skip the OIDC
provider delete if other repos/roles in the account still use it.

```bash
# 1. Delete the ECR repos (--force also deletes any images still in them)
aws ecr delete-repository \
  --repository-name charts/myapp \
  --force \
  --region ap-south-1

aws ecr delete-repository \
  --repository-name myapp \
  --force \
  --region ap-south-1

# 2. Remove the scoped policy, then the role itself
aws iam delete-role-policy \
  --role-name github-actions-ecr-push \
  --policy-name ecr-push-scoped

aws iam delete-role \
  --role-name github-actions-ecr-push

# 3. Delete the OIDC provider — only if nothing else in the account depends on it
#    (check first: aws iam list-open-id-connect-providers)
aws iam delete-open-id-connect-provider \
  --open-id-connect-provider-arn arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com
```

Also remember to remove the `GITOPS_REPO_TOKEN` secret from the repo settings
if you're decommissioning the pipeline entirely
(Settings → Secrets and variables → Actions).

## What's intentionally NOT here yet

- The GitOps repo itself (ArgoCD Application manifests, qa/uat/prod values)
- ArgoCD install/config
- Promotion PRs (dev → qa → uat → prod) with approval gates

That's stage 3 — the gitops-repo layout and ArgoCD Application manifests from
the earlier architecture doc slot in directly here, consuming exactly the
image tag + chart version this pipeline now produces.
