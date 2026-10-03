# woocommerce-agent-connector

A read-only WooCommerce connector for [Razorpay Agent Studio](https://razorpay.com/), exposed as an [MCP](https://modelcontextprotocol.io) server. It lets an Agent Studio agent look up orders, products (inventory), and customers in a WooCommerce store via the WooCommerce REST API v3.

## What the agent can do

The connector exposes 9 read-only tools over MCP:

**Orders**
- `list_orders` — list recent orders, optionally filtered by status (`pending`, `processing`, `on-hold`, `completed`, `cancelled`, `refunded`, `failed`) or by customer ID.
- `get_order` — fetch the full detail of a single order by its ID (line items, totals, billing/shipping address, status).
- `search_orders` — find orders by customer email and/or a date range (useful for "what did this customer order last month").

**Products (inventory)**
- `list_products` — list products, optionally filtered by category or restricted to items currently in stock.
- `get_product` — fetch the full detail of a single product by its ID (price, stock quantity, stock status, description).
- `search_products` — find products by name, description, or SKU text search.

**Customers**
- `list_customers` — list registered customers.
- `get_customer` — fetch the full detail of a single customer by their ID.
- `search_customers` — find customers by name or email text search.

## What the agent cannot do

This connector is **strictly read-only**. It does not and cannot:

- Create, update, or cancel orders
- Create, update, or delete products, or change stock levels
- Process, capture, or refund payments
- Create, update, or delete customers
- Access private/draft products or orders not exposed by the REST API
- Read subscription data (WooCommerce Subscriptions is a separate plugin/API not covered here)
- Read coupons, shipping settings, tax settings, or any store configuration
- Write, upload, or delete any data in the store

If an agent needs to take an action beyond reading data, this connector is the wrong tool for the job — it intentionally has no write primitives.

## Authentication setup

WooCommerce authenticates REST API requests with a **consumer key / consumer secret** pair sent as HTTP Basic auth. To generate a key pair:

1. In wp-admin, go to **WooCommerce → Settings → Advanced → REST API**.
2. Click **Add key**.
3. Give it a description (e.g. "Agent Studio connector"), select a user, and set **Permissions** to **Read** — this connector never needs Write access.
4. Click **Generate API key**.
5. Copy the **Consumer key** and **Consumer secret** — WooCommerce only shows the secret once.

Credentials are loaded exclusively from environment variables (see below). They are never hardcoded, logged, or committed to source control.

## Environment variables

| Variable | Description | Example |
|---|---|---|
| `WC_BASE_URL` | Base URL of the WooCommerce site (no trailing slash) | `https://mystore.com` |
| `WC_CONSUMER_KEY` | REST API consumer key, generated above | `ck_xxxxxxxxxxxxxxxx` |
| `WC_CONSUMER_SECRET` | REST API consumer secret, generated above | `cs_xxxxxxxxxxxxxxxx` |

All three are required. If any is missing, the connector raises a `MissingCredentialsError` naming exactly which variable is missing — it will not run with partial or default credentials.

## Setup and run

```bash
# 1. Copy the example env file and fill in your WooCommerce credentials
cp .env.example .env

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the MCP server (reads .env via python-dotenv, speaks MCP over stdio)
python mcp_server.py
```

Point your Agent Studio MCP client configuration at this command (`python mcp_server.py`, run from this directory) so the agent can discover and call the 9 tools listed above.

## Local testing with Docker

No live WooCommerce store or WooCommerce.com account is required to test this connector — `docker-compose.yml` spins up a local WordPress + MySQL stack you can install WooCommerce into.

```bash
docker compose up -d
```

Then:

1. Wait ~30-60 seconds for WordPress to finish initializing, then open [http://localhost:8080/wp-admin](http://localhost:8080/wp-admin) (user: `admin`, pass: `adminpassword` — see `docker-compose.yml`).
2. Install and activate WooCommerce:
   ```bash
   docker compose exec wordpress wp plugin install woocommerce --activate --allow-root
   ```
   (or manually: **Plugins → Add New** → search "WooCommerce" → **Install** → **Activate**, then click through the setup wizard.)
3. Generate REST API keys at **WooCommerce → Settings → Advanced → REST API** as described above, with **Read** permissions.
4. Put the generated key/secret into your `.env` file, with `WC_BASE_URL=http://localhost:8080`.
5. Run `python mcp_server.py` as above, or run the test suite against mocked responses with `pytest` (the test suite does not require Docker or a live store at all).

## Rate limits

WooCommerce does not publish a hard, documented rate limit for the REST API — limits depend on the hosting environment (e.g. a managed host's web server/WAF may throttle independently). This connector is defensive regardless:

- A local **token bucket rate limiter** caps outgoing requests at **25 requests/second** (capacity 25), so the connector itself never bursts past that rate even if the agent calls tools in a tight loop.
- On an HTTP **429** response from WooCommerce, the client retries with **exponential backoff plus jitter** (`2^attempt` seconds + random jitter), up to **3 attempts**, before giving up and raising an error with the status code and response body.
- Every request has a **10 second timeout** to avoid hanging indefinitely on a slow or unresponsive store.
- Any other non-2xx response (401, 404, 500, etc.) raises immediately with the status code and response body — it is not retried, since retrying a non-rate-limit error is unlikely to help and could mask a real problem.

## Assumptions and limitations

- **Read-only.** By design, this connector only issues GET requests. No order, product, or customer data in WooCommerce is ever created, modified, or deleted by this connector.
- **WooCommerce REST API v3** (`/wp-json/wc/v3/...`) is assumed. Older API versions (v1/v2) are not supported.
- **Tested against WooCommerce 8.x** running on WordPress, via the local Docker Compose stack described above. Other versions implementing the same v3 REST API contract should work but are not explicitly verified.
- Pagination is controlled per-call via `limit`/`offset` (mapped to WooCommerce's `per_page`/`offset` query params); there is no automatic "fetch everything" behavior, to avoid an agent accidentally pulling a store's entire order history in one call.
- `search_orders`/`search_products`/`search_customers` rely on WooCommerce's built-in `search` query parameter, which does a broad text match (not a structured query) — expect reasonable-but-not-exact-SQL-match results, consistent with how WooCommerce's own admin search behaves.
- Credentials are read only from environment variables (optionally via a local `.env` file through `python-dotenv`); they are never hardcoded or logged.
