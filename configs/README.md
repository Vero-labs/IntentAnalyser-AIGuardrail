# Gateway Config Packs

These files let you run the gateway in different environments with local, file-based config.

## Layout
- `local/guardrail.config.yaml`
- `staging/guardrail.config.yaml`
- `prod/guardrail.config.yaml`
- `policies/main.yaml`
- `<env>/.env.gateway`

## Run with local files (no copy required)

```bash
export GUARDRAIL_CONFIG_PATH="$PWD/configs/local/guardrail.config.yaml"
export GUARDRAIL_POLICY_PATH="$PWD/configs/policies/main.yaml"
export GUARDRAIL_ENV_FILE="$PWD/configs/local/.env.gateway"
python -m app.main
```

## Switch environment
Replace `local` with `staging` or `prod` in the paths above.
