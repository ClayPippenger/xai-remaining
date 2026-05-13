# Security Policy

## Reporting A Security Issue

Please report suspected security issues privately to the project maintainer.

Do not open public issues that contain Management Keys, team IDs, billing payloads, screenshots with private account data, or any other sensitive information.

## Secrets

xAI Remaining reads credentials only from environment variables:

- `XAI_MGMT_KEY`
- `XAI_TEAM_ID`

The app should not write secrets to config files, cache files, diagnostics, logs, or built artifacts. Diagnostics and debug modes should print only whether credentials are present, never their values.

## Supported Versions

Security fixes are provided for the latest version on the default branch unless otherwise stated.
