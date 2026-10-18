# Support demo

A small read-only customer support assistant for the fictional LumaShop product.
It uses the existing Code Assistance OpenAI configuration and its `.env` key lookup.
There is no real authentication: selecting a user only chooses the demo identity.

From the repository root, with the project environment installed:

```sh
.venv/bin/python -m support_demo
```

Select Jane and ask `Почему не работает оплата?`. The assistant should use the
shared `INC-101` incident and report its current `Уже чиним` status, without
promising a resolution time. Ask `Почему не начислены бонусы за ноутбук?` to
see Jane's personal ticket. Select Alex or Maria to verify that Jane's tickets
are not available to other users.
Use `/exit` to end the session.

The CLI reads demo identities and tickets through its local stdio MCP server.
The model is instructed to call `list_visible_tickets` for every question and
may also call `get_user` when a profile is needed. Ticket records are filtered
to the selected user and shared incidents before embedding search.
Only the explicit FAQ and product documents are indexed in memory; no index or
conversation history is written to disk. The endpoint and data-sharing notice
are shown before the first OpenAI request.
Source IDs are checked inside the application and removed from customer-facing
answers. Internal file paths are not included in model prompts or tool results.
