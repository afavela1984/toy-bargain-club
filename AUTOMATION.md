# Toy Bargain Club implementation checkpoint

Status: implementation branch prepared for review; not merged or operational.
The original root index.html and live site remain unchanged. The baseline is commit
98d34527a13fc4c624f21a76fc4bc36afc71bd46, also retained on the local backup branch
backup/pre-automation-2026-10-19. The repository's entire existing history was cloned.

## Implemented

- Preserve the vintage Christmas styling/background and original shopping controls in templates/site.html.
- Official Best Buy API adapter; no scraping or invented listings.
- Conservative requirements: online available, new, no restricted display price,
  selected recognized brand, toy taxonomy, explicit supported age evidence 3–17,
  at least 25% discount and $5 savings. Maximum 100 listings; no minimum filler.
- Savings explicitly labeled retailer-advertised, not independently verified history.
- Genuine product image and product URL taken from the same API record, HTTPS host allowlists,
  remote image display with textual fallback, no copied retailer image files.
- Exact unrounded discount filtering; floor displayed percentages to avoid overstating.
- API timeout, bounded retries and request budget. Up to 20 pages of 100 on-sale
  products in retailer discount order, one request per second. This bounded catalog
  sample can miss worthwhile toys; it is not full multi-retailer coverage.
- Last success survives failures for 48 hours; stale warning after 30 hours.
  A successful zero-result response clears old deals. Missing credentials never
  masquerade as a successful refresh. Cache errors do not expose request URLs.
- Proposed daily workflow at 13:00 UTC = 06:00 Phoenix, manual dispatch,
  serialized publication, minimal job permissions, public build-marker verification.
- Retailer data excluded from Git; successful temporary state artifact retention
  two days; Pages upload artifact one day. Failed refreshes don't renew state artifacts.
- Health job fails if refresh or publication is incomplete even if site generation succeeds.

## Deployment blockers and important limitation

1. GitHub integration returned HTTP 403 Resource not accessible by integration for
   both correctly formed branch creation and blob creation. Account permissions in
   repository metadata are not equivalent to the integration's effective write grant.
   Browser sign-in subsequently succeeded and browser edits work on the isolated
   implementation/automation-completion branch. No permissions have been changed.
2. No Best Buy developer key was available. The API has not been called with live
   credentials. Store any eventual credential in GitHub Actions secrets as
   BESTBUY_API_KEY, never in chat or tracked files.
3. Best Buy API terms limit temporary caching to 72 hours. A static Pages deployment
   remains retrievable even after JavaScript hides expired cards; artifacts and old
   deployment versions also need retention controls. This draft intentionally gates
   deployment with RETAILER_DISPLAY_APPROVED and is NOT a compliant live-data rollout
   by itself. Before enabling, implement a server-side expiring data endpoint that
   never writes retailer content into immutable site versions, or obtain express
   retailer permission for this static publishing/retention design. Do not simply
   set the variable as a shortcut. Scheduled cleanup alone is not a TTL guarantee.
4. Pages must use GitHub Actions as its publishing source for deploy-pages. Inspect
   existing configuration and obtain approval before changing account/access settings.
5. After those prerequisites, run workflow_dispatch, verify live API results and
   exact product photo/model correspondence, verify the returned public build ID,
   then perform mobile browser QA. Do not claim any of these checks already passed.

## Verification performed

Run `python -m unittest discover -s tests -v` and `node tests/test_filters.cjs`.
Python tests exercise selection, missing/invalid fields, discount boundaries,
cache expiry, pagination, rate-limit retry, secret suppression and HTML escaping.
The JS test executes the actual embedded script against a DOM test double for
search, age, price, discount, sort, favorites, reset and no results.
Missing-key build was exercised and produced an explicit unavailable status with
zero offers. JavaScript syntax passed Node's parser.
GitHub Actions run 39198214467 on the implementation branch verified both test
suites and the missing-credential build. Build passed; deploy was skipped; health
failed as intended because no live refresh occurred.
No real retailer prices, product links or photos were validated. Pages
republication and actual iPhone rendering have not been verified.
Browser preview is unavailable in this runtime's supported Sites preview workflow.

## Sources investigated (2026-10-19 UTC)

- Best Buy API: https://developer.bestbuy.com/apis
- Best Buy terms: https://developer.bestbuy.com/legal
- Fields and query docs: https://bestbuyapis.github.io/api-documentation/
- Walmart affiliate APIs: https://walmart.io/docs/affiliates/introduction
  Requires authorized access; no Walmart connector implemented.
- Target: https://partners.target.com/faqs
  Requires acceptance into Target Partners; feed availability/rights must be confirmed.
- Amazon Creators API: https://affiliate-program.amazon.com/creatorsapi/docs/en-us/onboarding/register-for-creators-api
  Requires a reviewed and finally accepted Associates account and Creators API access.
- LEGO direct program/feed access not confirmed; LEGO-brand toys can qualify through
  Best Buy. No direct LEGO retailer connector implemented.

No new accounts, subscriptions, purchases, affiliate enrollments or permission
changes were performed. No secrets were printed or written into project files.
