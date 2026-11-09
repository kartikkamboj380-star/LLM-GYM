# Design Arena inspection and authorization boundary

Inspection date: **2026-11-09**. Websites can change; re-check the official pages before relying on these notes.

## Publicly observed features

The public homepage describes prompt-based creation and comparison across websites, code art, code-to-video, PDF, spreadsheets, images, video, games, text-to-speech, slides, 3D assets, mobile apps, SVG, UI components, data visualizations, and ASCII art. It also links to projects, leaderboards, models, blog, and methodology pages.

The public `/auth` page exposes sign-up/login UI. The privacy notice discusses optional social-media login data and Google API/One Tap usage. That is **not enough evidence to assert a definitive current list of login methods**. This project therefore does not claim that a specific OAuth provider is universally available and does not automate the auth page.

## Officially documented API

Sources:

- [Design Arena API introduction](https://docs.designarena.ai/introduction)
- [Official API overview](https://docs.designarena.ai/api-reference/overview)
- [Official quickstart](https://docs.designarena.ai/quickstart)
- [Public homepage](https://www.designarena.ai/)

The docs specify base URL `https://www.designarena.ai/api/v1`, bearer authentication, and these endpoints:

- `GET /arenas`
- `GET /models`
- `GET /leaderboard/{arena}/{category}`

API keys require an application and approval. The docs say strict rate limits are not currently enforced but unreasonable use can lead to revocation. They also document CDN caching. Be conservative, cache responses when appropriate, and follow attribution requirements.

`app/designarena/client.py` wraps only those three documented GET operations. It has no generic arbitrary-path method. Leaderboard parameters are URL encoded, and the key remains on the backend.

## What is not authorized by this inspection

No official documentation was found for programmatically logging in, submitting generation prompts, voting, creating projects, or managing accounts. A browser's internal network requests are not a public API contract. Consequently:

- no undocumented endpoint has been added;
- no cookies, session tokens, or login credentials are collected;
- no CAPTCHA, bot detection, rate limit, or account restriction is bypassed;
- no Design Arena browser flow is supplied;
- no automated account creation or OTP handling is connected to Design Arena.

Without an official write interface and explicit authorization, reliable and permitted browser automation of those actions cannot be claimed. Manual use through the normal website remains subject to its terms.

## Safe alternative

Use this repository's local chat UI for your own model-provider accounts and owned workflows. Use the official Design Arena read-only API for leaderboard learning/comparison after approval. If Design Arena publishes additional APIs or grants written test permission in the future, add a narrowly scoped adapter against that documentation and update these notes.
