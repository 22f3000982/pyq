# MauryaHub public-site setup

Deploy this code to the Render service behind mauryahub.in. Confirm that its repository and main branch are correct before deployment.

Optional Render environment variables:

- `PUBLIC_SITE_URL=https://mauryahub.in` (default already provided). Use an origin only, without a trailing path.
- `GOOGLE_SITE_VERIFICATION`: the content value from a Search Console HTML verification tag. DNS Domain-property verification still requires GoDaddy's TXT record; this variable does not replace it.
- `ADSENSE_PUBLISHER_ID=pub-XXXXXXXXXXXXXXXX`: your actual 16-digit publisher ID. This supplies the AdSense account verification meta tag and `/ads.txt`. Do not use an example ID.

No advertising script or consent management platform is activated by these settings. Advertising activation needs a separate placement and consent setup. Keep the privacy policy consistent with actual integrations.

After deploying:
1. Open `/study`, `/contact`, `/privacy` and `/content-policy`; verify actual page contents.
2. Confirm `/robots.txt` is plain text and `/sitemap.xml` is XML, not the app shell.
3. Submit `https://mauryahub.in/sitemap.xml` in Search Console and inspect a real public paper URL.
4. Add mauryahub.in in AdSense; verify using the supported account method. Review `/ads.txt` once the publisher ID is configured.
5. Unknown routes must return HTTP 404. Private attempt/admin pages use noindex.

Personal correspondence about paper sharing is not included in the repository or published. The content policy does not assert institutional endorsement or a redistribution licence.
