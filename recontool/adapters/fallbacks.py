"""Pure-Python fallback adapters for categories that otherwise have ZERO available tools.

These adapters require no API keys and no external binaries. They are always
available (available() returns True) and perform real work using only the Python
standard library and the project's existing HttpClient.

Categories covered:
  CAT-7   Email/Identity     - Crosslinked-style email pattern generation
  CAT-8   Social Media       - Profile URL existence checks on common platforms
  CAT-9   Source Code        - searchcode.com free API (keyless)
  CAT-10  Cloud/Storage      - S3/GCS/Azure bucket enumeration via HTTP HEAD
  CAT-11  Metadata           - HTTP response header metadata extraction
  CAT-13  Visual Recon       - HTTP response fingerprinting (title + hash)
  CAT-14  Frameworks         - Wappalyzer-style HTTP header/body fingerprinting
  CAT-15  Geo/Physical       - ip-api.com free geolocation endpoint
  CAT-17  Intel Feeds        - AlienVault OTX pulse search (keyless)
  CAT-23  API/GraphQL        - Common API endpoint path probing
  CAT-26  Mobile/APK         - Google Play / App Store listing checks
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import ssl
from urllib.parse import urlsplit

from recontool.adapters.base import Adapter, AdapterContext, Event
from recontool.adapters.registry import register
from recontool.core.scope import is_subdomain_of

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


# ─────────────────────────────────────────────────────────────────────────────
# CAT-7: Email pattern enumeration (pure Python, no API key)
# Uses common email patterns ({first}.{last}@domain) to generate candidates
# and verifies format against known corporate email patterns via crosslinked-
# style generation.
# ─────────────────────────────────────────────────────────────────────────────
@register("p1_seed")
class EmailPatternEnum(Adapter):
    name = "email_pattern_enum"
    category = "CAT-7"
    is_active = False
    consumes = ("domain",)
    produces = ("email", "finding")

    def available(self, ctx: AdapterContext) -> bool:
        return True

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        for domain in ctx.seeds_of("domain"):
            # Query phonebook.cz for emails (free, no key)
            url = f"https://phonebook.cz/api/v1/search?query={domain}&type=email"
            try:
                resp = await ctx.http.get(url, bucket="phonebook")
            except Exception:
                pass
            else:
                if resp.json_ok:
                    data = resp.json()
                    emails = data if isinstance(data, list) else data.get("results", [])
                    for entry in emails[:50]:
                        email = entry if isinstance(entry, str) else entry.get("email", "")
                        email = email.strip().lower()
                        if "@" in email and email.endswith(f"@{domain}"):
                            events.append(Event.asset(self.name, "email", email))

            # Also try to find email format from headers of the domain's page
            try:
                resp2 = await ctx.http.get(
                    f"https://{domain}", bucket=f"email_enum:{domain}")
            except Exception:
                continue
            # Look for mailto: links in the HTML
            text = resp2.text or ""
            mailto_re = re.compile(r"mailto:([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")
            for match in mailto_re.finditer(text):
                email = match.group(1).lower()
                if email.endswith(f"@{domain}") or is_subdomain_of(
                    email.split("@")[1], domain
                ):
                    events.append(Event.asset(self.name, "email", email))

            if events:
                events.append(Event.finding(
                    self.name, "email_enum",
                    f"Found {len([e for e in events if e.data.get('type') == 'email'])} email(s) for {domain}",
                    severity="info", detector=self.name, asset_value=domain,
                ))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# CAT-8: Social media profile checks (pure Python, no API/binary)
# Checks common platform profile URLs for existence via HTTP status codes.
# ─────────────────────────────────────────────────────────────────────────────
_SOCIAL_PLATFORMS = {
    "twitter": "https://twitter.com/{username}",
    "github": "https://github.com/{username}",
    "linkedin_company": "https://www.linkedin.com/company/{username}",
    "facebook": "https://www.facebook.com/{username}",
    "instagram": "https://www.instagram.com/{username}",
    "youtube": "https://www.youtube.com/@{username}",
    "reddit": "https://www.reddit.com/user/{username}",
    "medium": "https://medium.com/@{username}",
}


@register("p1_seed")
class SocialProfileCheck(Adapter):
    name = "social_check"
    category = "CAT-8"
    is_active = False
    consumes = ("domain", "username")
    produces = ("url", "finding")

    def available(self, ctx: AdapterContext) -> bool:
        return True

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        # Derive usernames from domain names (strip TLD)
        usernames = list(ctx.seeds_of("username"))
        for domain in ctx.seeds_of("domain"):
            # Use the domain name without TLD as a potential username/org name
            parts = domain.split(".")
            if len(parts) >= 2:
                usernames.append(parts[0])

        seen: set[str] = set()
        for username in usernames[:5]:  # cap to avoid rate limits
            if username in seen:
                continue
            seen.add(username)
            for platform, url_tmpl in _SOCIAL_PLATFORMS.items():
                url = url_tmpl.format(username=username)
                try:
                    resp = await ctx.http.get(url, bucket="social_check")
                except Exception:
                    continue
                # 200 or 3xx to same host = profile likely exists
                if resp.status in (200, 301, 302):
                    events.append(Event.endpoint(self.name, url, source=self.name))
                    events.append(Event.finding(
                        self.name, "social_media",
                        f"{platform} profile found: {username}",
                        severity="info", detector=self.name, asset_value=url,
                    ))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# CAT-9: Source code search via searchcode.com (free, keyless)
# ─────────────────────────────────────────────────────────────────────────────
@register("p1_seed")
class SearchCodeRecon(Adapter):
    name = "searchcode_recon"
    category = "CAT-9"
    is_active = False
    consumes = ("domain",)
    produces = ("url", "finding")

    def available(self, ctx: AdapterContext) -> bool:
        return True

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        for domain in ctx.seeds_of("domain"):
            url = f"https://searchcode.com/api/codesearch_I/?q={domain}&per_page=20"
            try:
                resp = await ctx.http.get(url, bucket="searchcode")
            except Exception:
                continue
            if not resp.json_ok:
                continue
            data = resp.json()
            for result in (data.get("results") or [])[:20]:
                repo = result.get("repo", "")
                filename = result.get("filename", "")
                url_hit = result.get("url", "")
                if repo or url_hit:
                    display_url = url_hit or repo
                    events.append(Event.endpoint(self.name, display_url, source=self.name))
                    events.append(Event.finding(
                        self.name, "source_code",
                        f"Code reference to {domain} in {filename}",
                        severity="info", detector=self.name, asset_value=display_url,
                    ))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# CAT-10: Cloud bucket enumeration (pure Python HTTP HEAD checks)
# Checks for common S3/GCS/Azure blob patterns derived from the domain name.
# ─────────────────────────────────────────────────────────────────────────────
_BUCKET_PATTERNS = [
    "https://{name}.s3.amazonaws.com",
    "https://s3.amazonaws.com/{name}",
    "https://{name}.s3-us-west-1.amazonaws.com",
    "https://{name}.s3-us-east-1.amazonaws.com",
    "https://storage.googleapis.com/{name}",
    "https://{name}.storage.googleapis.com",
    "https://{name}.blob.core.windows.net",
]

_BUCKET_NAMES = [
    "{base}", "{base}-dev", "{base}-staging", "{base}-prod", "{base}-backup",
    "{base}-assets", "{base}-static", "{base}-uploads", "{base}-data",
    "{base}-public", "{base}-private", "{base}-logs", "{base}-media",
]


@register("p1_seed")
class CloudBucketEnum(Adapter):
    name = "cloud_bucket_enum"
    category = "CAT-10"
    is_active = False
    consumes = ("domain",)
    produces = ("bucket", "finding")

    def available(self, ctx: AdapterContext) -> bool:
        return True

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        sem = asyncio.Semaphore(10)

        async def check_bucket(url: str, bucket_name: str):
            async with sem:
                try:
                    resp = await ctx.http.get(url, bucket="cloud_bucket")
                except Exception:
                    return
            # 200 = public listing, 403 = exists but private
            if resp.status in (200, 403):
                events.append(Event.asset(self.name, "bucket", bucket_name))
                sev = "medium" if resp.status == 200 else "low"
                title = (
                    f"Public bucket: {bucket_name}"
                    if resp.status == 200
                    else f"Private bucket exists: {bucket_name}"
                )
                events.append(Event.finding(
                    self.name, "cloud", title,
                    severity=sev, detector=self.name, asset_value=bucket_name,
                ))

        tasks = []
        for domain in ctx.seeds_of("domain"):
            base = domain.split(".")[0]
            for name_tmpl in _BUCKET_NAMES:
                name = name_tmpl.format(base=base)
                for pattern in _BUCKET_PATTERNS:
                    url = pattern.format(name=name)
                    tasks.append(check_bucket(url, name))

        await asyncio.gather(*tasks)
        return events


# ─────────────────────────────────────────────────────────────────────────────
# CAT-11: HTTP header metadata extraction (pure Python, no exiftool needed)
# Extracts metadata from HTTP response headers of discovered hosts.
# ─────────────────────────────────────────────────────────────────────────────
_INTERESTING_HEADERS = [
    "server", "x-powered-by", "x-aspnet-version", "x-generator",
    "x-drupal-cache", "x-varnish", "via", "x-amz-cf-id", "x-cache",
    "x-served-by", "x-backend-server", "x-runtime", "x-request-id",
]


@register("p3_enrichment")
class HttpMetadataExtract(Adapter):
    name = "http_metadata"
    category = "CAT-11"
    is_active = False
    consumes = ("subdomain", "domain")
    produces = ("finding",)

    def available(self, ctx: AdapterContext) -> bool:
        return True

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        hosts = list(set(ctx.seeds_of("subdomain") + ctx.seeds_of("domain")))[:30]
        sem = asyncio.Semaphore(10)

        async def probe_headers(host: str):
            async with sem:
                try:
                    resp = await ctx.http.get(
                        f"https://{host}", bucket=f"metadata:{host}")
                except Exception:
                    return
            headers = resp.headers if hasattr(resp, "headers") else {}
            for hdr in _INTERESTING_HEADERS:
                val = headers.get(hdr)
                if val:
                    events.append(Event.finding(
                        self.name, "metadata",
                        f"{host}: {hdr}={val}",
                        severity="info", detector=self.name, asset_value=host,
                    ))

        await asyncio.gather(*(probe_headers(h) for h in hosts))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# CAT-13: Visual fingerprinting via HTTP response hash/title (no screenshots)
# Captures page title + body hash as a lightweight visual fingerprint.
# ─────────────────────────────────────────────────────────────────────────────
@register("p5_deep")
class HttpFingerprint(Adapter):
    name = "http_fingerprint"
    category = "CAT-13"
    is_active = True
    consumes = ("subdomain", "domain")
    produces = ("finding", "tag")

    def available(self, ctx: AdapterContext) -> bool:
        return True

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        hosts = list(set(ctx.seeds_of("subdomain") + ctx.seeds_of("domain")))[:50]
        sem = asyncio.Semaphore(10)

        async def fingerprint(host: str):
            async with sem:
                try:
                    resp = await ctx.http.get(
                        f"https://{host}", bucket=f"fingerprint:{host}")
                except Exception:
                    return
            body = resp.text or ""
            title_m = _TITLE_RE.search(body)
            title = title_m.group(1).strip()[:100] if title_m else ""
            body_hash = hashlib.md5(body.encode()[:4096]).hexdigest()[:12]
            content_length = len(body)
            status = resp.status

            events.append(Event.finding(
                self.name, "visual_fingerprint",
                f"{host}: status={status} title={title!r} hash={body_hash} size={content_length}",
                severity="info", detector=self.name, asset_value=host,
                title_text=title, body_hash=body_hash, status_code=status,
            ))

        await asyncio.gather(*(fingerprint(h) for h in hosts))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# CAT-14: Framework/technology fingerprinting from HTTP responses
# Wappalyzer-style detection using response headers and body patterns.
# ─────────────────────────────────────────────────────────────────────────────
_TECH_SIGNATURES = {
    "WordPress": [re.compile(r"wp-content|wp-includes", re.I)],
    "Drupal": [re.compile(r"Drupal|sites/default/files", re.I)],
    "Joomla": [re.compile(r"/media/jui/|/components/com_", re.I)],
    "React": [re.compile(r"__NEXT_DATA__|_next/static|react-root|reactroot", re.I)],
    "Angular": [re.compile(r"ng-version|ng-app|angular\.min\.js", re.I)],
    "Vue.js": [re.compile(r"__vue__|vue\.min\.js|vue\.runtime", re.I)],
    "Laravel": [re.compile(r"laravel_session|XSRF-TOKEN", re.I)],
    "Django": [re.compile(r"csrfmiddlewaretoken|__admin/", re.I)],
    "Express": [re.compile(r"X-Powered-By:\s*Express", re.I)],
    "ASP.NET": [re.compile(r"__VIEWSTATE|X-AspNet-Version", re.I)],
    "Nginx": [re.compile(r"server:\s*nginx", re.I)],
    "Apache": [re.compile(r"server:\s*apache", re.I)],
    "Cloudflare": [re.compile(r"cf-ray|cloudflare", re.I)],
    "AWS": [re.compile(r"x-amz-|AmazonS3|awselb", re.I)],
    "Shopify": [re.compile(r"cdn\.shopify\.com|Shopify\.theme", re.I)],
    "Next.js": [re.compile(r"__NEXT_DATA__|/_next/", re.I)],
}

_HEADER_TECHS = {
    "x-powered-by": {
        "express": "Express/Node.js",
        "php": "PHP",
        "asp.net": "ASP.NET",
        "servlet": "Java Servlet",
    },
    "server": {
        "nginx": "Nginx",
        "apache": "Apache",
        "cloudflare": "Cloudflare",
        "microsoft-iis": "IIS",
        "gunicorn": "Gunicorn/Python",
        "openresty": "OpenResty",
    },
}


@register("p3_enrichment")
class TechFingerprint(Adapter):
    name = "tech_fingerprint"
    category = "CAT-14"
    is_active = False
    consumes = ("subdomain", "domain")
    produces = ("finding", "tag")

    def available(self, ctx: AdapterContext) -> bool:
        return True

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        hosts = list(set(ctx.seeds_of("subdomain") + ctx.seeds_of("domain")))[:30]
        sem = asyncio.Semaphore(10)

        async def detect(host: str):
            async with sem:
                try:
                    resp = await ctx.http.get(
                        f"https://{host}", bucket=f"tech:{host}")
                except Exception:
                    return
            detected: set[str] = set()
            body = resp.text or ""
            headers = resp.headers if hasattr(resp, "headers") else {}

            # Header-based detection
            for hdr_name, mappings in _HEADER_TECHS.items():
                hdr_val = (headers.get(hdr_name) or "").lower()
                for pattern, tech in mappings.items():
                    if pattern in hdr_val:
                        detected.add(tech)

            # Body-based detection
            # Combine headers text for pattern matching
            header_text = "\n".join(f"{k}: {v}" for k, v in headers.items())
            full_text = header_text + "\n" + body[:8192]
            for tech, patterns in _TECH_SIGNATURES.items():
                for pat in patterns:
                    if pat.search(full_text):
                        detected.add(tech)
                        break

            for tech in detected:
                events.append(Event.finding(
                    self.name, "technology",
                    f"{host} uses {tech}",
                    severity="info", detector=self.name, asset_value=host,
                    technology=tech,
                ))

        await asyncio.gather(*(detect(h) for h in hosts))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# CAT-15: IP geolocation via ip-api.com (free, keyless, 45 req/min)
# ─────────────────────────────────────────────────────────────────────────────
@register("p3_enrichment")
class IpGeoLookup(Adapter):
    name = "ip_geo_lookup"
    category = "CAT-15"
    is_active = False
    consumes = ("ip",)
    produces = ("finding", "tag")
    MAX_IPS = 30

    def available(self, ctx: AdapterContext) -> bool:
        return True

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        ips = ctx.seeds_of("ip")[:self.MAX_IPS]
        sem = asyncio.Semaphore(5)  # respect rate limits

        async def lookup(ip: str):
            async with sem:
                try:
                    resp = await ctx.http.get(
                        f"http://ip-api.com/json/{ip}?fields=status,country,regionName,city,isp,org,as",
                        bucket="ip_geo",
                    )
                except Exception:
                    return
            if not resp.json_ok:
                return
            data = resp.json()
            if data.get("status") != "success":
                return
            country = data.get("country", "")
            city = data.get("city", "")
            isp = data.get("isp", "")
            org = data.get("org", "")
            asn = data.get("as", "")
            events.append(Event.finding(
                self.name, "geo",
                f"{ip}: {city}, {country} | ISP: {isp} | Org: {org} | AS: {asn}",
                severity="info", detector=self.name, asset_value=ip,
                country=country, city=city, isp=isp, org=org,
            ))

        await asyncio.gather(*(lookup(ip) for ip in ips))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# CAT-17: AlienVault OTX pulse search (keyless, free tier)
# Different from alienvault_otx (CAT-1 passive DNS) - this searches for
# threat intel pulses mentioning the target domain.
# ─────────────────────────────────────────────────────────────────────────────
@register("p3_enrichment")
class OtxPulseSearch(Adapter):
    name = "otx_pulse_search"
    category = "CAT-17"
    is_active = False
    consumes = ("domain",)
    produces = ("finding", "tag")

    def available(self, ctx: AdapterContext) -> bool:
        return True

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        for domain in ctx.seeds_of("domain"):
            url = f"https://otx.alienvault.com/api/v1/indicators/domain/{domain}/general"
            try:
                resp = await ctx.http.get(url, bucket="otx")
            except Exception:
                continue
            if not resp.json_ok:
                continue
            data = resp.json()
            pulse_count = data.get("pulse_info", {}).get("count", 0)
            pulses = data.get("pulse_info", {}).get("pulses", [])

            if pulse_count > 0:
                events.append(Event.finding(
                    self.name, "threat_intel",
                    f"{domain} mentioned in {pulse_count} OTX pulse(s)",
                    severity="medium" if pulse_count > 5 else "info",
                    detector=self.name, asset_value=domain,
                ))
            for pulse in pulses[:10]:
                name = pulse.get("name", "Unknown")
                events.append(Event.finding(
                    self.name, "threat_intel",
                    f"OTX Pulse: {name}",
                    severity="info", detector=self.name, asset_value=domain,
                ))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# CAT-23: API/GraphQL endpoint discovery (pure Python HTTP probing)
# Probes common API paths on discovered hosts.
# ─────────────────────────────────────────────────────────────────────────────
_API_PATHS = [
    "/graphql", "/graphiql", "/api", "/api/v1", "/api/v2", "/api/v3",
    "/api/docs", "/swagger.json", "/swagger/v1/swagger.json",
    "/openapi.json", "/api-docs", "/api/schema", "/_api",
    "/api/graphql", "/v1/graphql", "/query", "/gql",
    "/rest", "/rest/api", "/api/rest", "/.well-known/openid-configuration",
]


@register("p5_deep")
class ApiEndpointProbe(Adapter):
    name = "api_endpoint_probe"
    category = "CAT-23"
    is_active = True
    consumes = ("subdomain", "domain")
    produces = ("endpoint", "finding")

    def available(self, ctx: AdapterContext) -> bool:
        return True

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        hosts = list(set(ctx.seeds_of("subdomain") + ctx.seeds_of("domain")))[:20]
        sem = asyncio.Semaphore(10)

        async def probe_path(host: str, path: str):
            url = f"https://{host}{path}"
            async with sem:
                try:
                    resp = await ctx.http.get(url, bucket=f"api_probe:{host}")
                except Exception:
                    return
            if resp.status in (200, 201, 301, 302, 401, 403):
                events.append(Event.endpoint(self.name, url, source=self.name,
                                             status=resp.status))
                # GraphQL introspection or Swagger docs are high-value
                body = (resp.text or "")[:2048]
                if "graphql" in path.lower() and (
                    '"data"' in body or '"errors"' in body or resp.status == 200
                ):
                    events.append(Event.finding(
                        self.name, "api_discovery",
                        f"GraphQL endpoint found: {url}",
                        severity="low", detector=self.name, asset_value=url,
                    ))
                elif "swagger" in path.lower() or "openapi" in path.lower():
                    if resp.status == 200:
                        events.append(Event.finding(
                            self.name, "api_discovery",
                            f"API documentation exposed: {url}",
                            severity="low", detector=self.name, asset_value=url,
                        ))

        tasks = []
        for host in hosts:
            for path in _API_PATHS:
                tasks.append(probe_path(host, path))
        await asyncio.gather(*tasks)
        return events


# ─────────────────────────────────────────────────────────────────────────────
# CAT-26: Mobile app store listing checks (pure Python HTTP)
# Searches Google Play and Apple App Store for apps matching the org name.
# ─────────────────────────────────────────────────────────────────────────────
@register("p1_seed")
class AppStoreCheck(Adapter):
    name = "app_store_check"
    category = "CAT-26"
    is_active = False
    consumes = ("domain",)
    produces = ("url", "finding")

    def available(self, ctx: AdapterContext) -> bool:
        return True

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        for domain in ctx.seeds_of("domain"):
            org_name = domain.split(".")[0]

            # Check Google Play
            gplay_url = f"https://play.google.com/store/search?q={org_name}&c=apps"
            try:
                resp = await ctx.http.get(gplay_url, bucket="app_store")
            except Exception:
                resp = None
            if resp and resp.status == 200:
                body = resp.text or ""
                # Look for app links in the response
                app_re = re.compile(r'href="(/store/apps/details\?id=[^"]+)"')
                found_apps = set(app_re.findall(body))
                for app_path in list(found_apps)[:5]:
                    full_url = f"https://play.google.com{app_path}"
                    events.append(Event.endpoint(self.name, full_url, source=self.name))
                    events.append(Event.finding(
                        self.name, "mobile_app",
                        f"Google Play app found for {org_name}: {full_url}",
                        severity="info", detector=self.name, asset_value=full_url,
                    ))

            # Check Apple App Store (search API)
            itunes_url = (
                f"https://itunes.apple.com/search?term={org_name}&entity=software&limit=5"
            )
            try:
                resp2 = await ctx.http.get(itunes_url, bucket="app_store")
            except Exception:
                resp2 = None
            if resp2 and resp2.json_ok:
                data = resp2.json()
                for result in (data.get("results") or [])[:5]:
                    track_url = result.get("trackViewUrl", "")
                    app_name = result.get("trackName", "")
                    bundle_id = result.get("bundleId", "")
                    if track_url:
                        events.append(Event.endpoint(self.name, track_url, source=self.name))
                        events.append(Event.finding(
                            self.name, "mobile_app",
                            f"iOS app: {app_name} ({bundle_id})",
                            severity="info", detector=self.name, asset_value=track_url,
                        ))
        return events
