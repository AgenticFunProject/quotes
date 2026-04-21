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

## Notes

- The create-quote requests use schedule IDs and payloads that match the seeded
  sample data in this repository.
- `GET /quotes/{id}` currently requires the stored quote's internal UUID.
  The API does not return that UUID from `POST /quotes`, so update the
  `quoteId` environment variable with an existing quote UUID before running
  `Get Quote by ID`.
- The service does not currently require authentication, so no secrets are
  stored in the collection.
