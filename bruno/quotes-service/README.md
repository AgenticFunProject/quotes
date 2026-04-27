# Bruno Collection for Quotes Service

This collection mirrors the current HTTP API exposed by the service.

## Environments

- `local` uses `http://localhost:8000`
- `azure-dev` uses `https://app-quotes-dev-371ad1.azurewebsites.net`

No live Azure environment could be confirmed from the current subscription, so
only the verified dev deployment is included.

## Requests Included

- `Health Check`
- `Create Quote - Standard Lane`
- `Create Quote - Heavy Cargo`
- `Get Quote by ID`
- `Get Quote by Reference`

## Notes

- The create-quote requests use schedule IDs and payloads that match the seeded
  sample data in this repository.
- `POST /quotes` returns both the stored quote UUID (`id`) and the human-facing
  `quoteReference`.
- Update the `quoteId` and `quoteReference` environment variables with an
  existing quote before running the lookup requests.
- The service does not currently require authentication, so no secrets are
  stored in the collection.
