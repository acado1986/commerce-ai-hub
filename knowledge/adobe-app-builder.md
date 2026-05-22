# Adobe App Builder Knowledge Notes

Use Adobe official docs as source of truth:
- Runtime actions: https://developer.adobe.com/app-builder/docs/guides/runtime_guides/
- Events and webhooks: https://developer.adobe.com/events/docs/
- API Mesh: https://developer.adobe.com/graphql-mesh-gateway/
- App structure and `aio` workflow: https://developer.adobe.com/app-builder/docs/getting_started/
- Developer Console projects: https://developer.adobe.com/console
- Secrets and configuration: https://developer.adobe.com/app-builder/docs/guides/runtime_guides/secrets/
- Logging and observability: https://developer.adobe.com/app-builder/docs/guides/application_logging/

Operational topics to include in architecture/planning:
- retries, timeouts, idempotency, error handling, and runtime limits.
- Commerce extensibility AI/coding-tools setup: `aio commerce extensibility app-setup`.
- Commerce extensibility AI tools refresh/manual setup inside a starter-kit project: `aio commerce extensibility tools-setup`.
- Generic App Builder project setup commands to consider when Commerce extensibility scaffolding is not required: `aio app init`, `aio app dev`, `aio app deploy`.
- API Mesh is an add-on capability for GraphQL source composition; include relevant `aio api-mesh:*` commands when selected.
