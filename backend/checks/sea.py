"""
sea.py
Prüft ob auf einer Seite aktive Kampagnen-Tags vorhanden sind.
Nutzt die Google Tag Manager API um den Container-Inhalt auszulesen.
"""

import os
import json
from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ── Konfiguration ─────────────────────────────────────────────────────────

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), '..', 'gtm_credentials.json')

GTM_CONTAINER_ID = 'GTM-53PLQ9'

# Tag-Typen die auf aktive Kampagnen hinweisen
CAMPAIGN_TAG_TYPES = {
    'awct':   'Google Ads Conversion Tracking',
    'adwords_remarketing':   'Google Ads Remarketing',
    'flc':    'Floodlight Counter (Google Marketing Platform)',
    'fls':    'Floodlight Sales (Google Marketing Platform)',
    'sp':     'Meta / Facebook Pixel',
    'linkedin': 'LinkedIn Insight Tag',
    'twitter_remarketing': 'X / Twitter Pixel',
}

# Tag-Namen die auf Kampagnen hinweisen (Freitext-Suche)
CAMPAIGN_NAME_PATTERNS = [
    'google ads', 'adwords', 'conversion',
    'meta pixel', 'facebook pixel', 'fbq',
    'linkedin insight', 'linkedin ads',
    'remarketing', 'retargeting',
]

# UTM-Parameter die auf Kampagnensteuerung hinweisen
UTM_PARAMS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term']


# ── GTM API ───────────────────────────────────────────────────────────────

def get_gtm_service():
    """Erstellt einen authentifizierten GTM API Client."""
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=['https://www.googleapis.com/auth/tagmanager.readonly']
    )
    return build('tagmanager', 'v2', credentials=creds)


def get_container_tags(service) -> list:
    """Lädt alle Tags aus dem GTM Container."""
    try:
        # Account-Liste abrufen
        accounts = service.accounts().list().execute()
        for account in accounts.get('account', []):
            containers = service.accounts().containers().list(
                parent=account['path']
            ).execute()
            for container in containers.get('container', []):
                if GTM_CONTAINER_ID in container.get('publicId', ''):
                    # Workspace abrufen
                    workspaces = service.accounts().containers().workspaces().list(
                        parent=container['path']
                    ).execute()
                    if workspaces.get('workspace'):
                        workspace_path = workspaces['workspace'][0]['path']
                        tags = service.accounts().containers().workspaces().tags().list(
                            parent=workspace_path
                        ).execute()
                        return tags.get('tag', [])
    except Exception as e:
        raise Exception(f"GTM API Fehler: {str(e)}")
    return []


# ── UTM-Check ─────────────────────────────────────────────────────────────

def check_utm_links(soup: BeautifulSoup) -> list:
    """Prüft ob interne Links UTM-Parameter enthalten."""
    utm_links = []
    for a in soup.find_all('a', href=True):
        href = a['href'].lower()
        if any(param in href for param in UTM_PARAMS):
            utm_links.append(a['href'])
    return utm_links


# ── Haupt-Check ───────────────────────────────────────────────────────────

def check_sea(soup: BeautifulSoup, base_url: str) -> dict:
    """
    Prüft ob aktive Kampagnen-Tags im GTM Container vorhanden sind
    und ob UTM-Parameter in Links auf der Seite vorkommen.
    """
    issues = []
    warnings = []
    passed = []
    campaign_tags = []
    gtm_available = False

    # ── GTM API Check ──────────────────────────────────────────────────────
    try:
        service = get_gtm_service()
        tags = get_container_tags(service)
        gtm_available = True

        for tag in tags:
            tag_type = tag.get('type', '').lower()
            tag_name = tag.get('name', '').lower()
            paused = tag.get('paused', False)

            # Nach bekannten Kampagnen-Tag-Typen suchen
            matched_type = None
            for code, label in CAMPAIGN_TAG_TYPES.items():
                if code in tag_type:
                    matched_type = label
                    break

            # Nach Kampagnen-Namen suchen
            if not matched_type:
                for pattern in CAMPAIGN_NAME_PATTERNS:
                    if pattern in tag_name:
                        matched_type = tag.get('name', 'Unbekannter Kampagnen-Tag')
                        break

            if matched_type:
                campaign_tags.append({
                    'name': tag.get('name'),
                    'type': matched_type,
                    'paused': paused,
                })

        if campaign_tags:
            active = [t for t in campaign_tags if not t['paused']]
            paused_tags = [t for t in campaign_tags if t['paused']]

            if active:
                for tag in active:
                    passed.append({
                        'code': 'CAMPAIGN_TAG_ACTIVE',
                        'message': f"Aktiver Kampagnen-Tag gefunden: {tag['name']} ({tag['type']})",
                    })
            if paused_tags:
                for tag in paused_tags:
                    warnings.append({
                        'code': 'CAMPAIGN_TAG_PAUSED',
                        'message': f"Pausierter Kampagnen-Tag: {tag['name']} ({tag['type']})",
                        'severity': 'info',
                    })
        else:
            warnings.append({
                'code': 'NO_CAMPAIGN_TAGS',
                'message': 'Keine aktiven Kampagnen-Tags im GTM Container gefunden.',
                'severity': 'info',
            })

    except Exception as e:
        warnings.append({
            'code': 'GTM_API_ERROR',
            'message': f"GTM API nicht erreichbar: {str(e)}",
            'severity': 'warning',
        })

    # ── UTM-Parameter Check ────────────────────────────────────────────────
    utm_links = check_utm_links(soup)
    if utm_links:
        passed.append({
            'code': 'UTM_LINKS_FOUND',
            'message': f"{len(utm_links)} Link(s) mit UTM-Parametern gefunden – aktive Kampagnensteuerung erkannt.",
        })
    else:
        warnings.append({
            'code': 'NO_UTM_LINKS',
            'message': 'Keine UTM-Parameter in Links auf der Seite gefunden.',
            'severity': 'info',
        })

    data = {
        'gtm_available': gtm_available,
        'campaign_tags': campaign_tags,
        'utm_links': utm_links[:10],
    }

    return _build_result(issues, warnings, passed, data)


def _build_result(issues, warnings, passed, data) -> dict:
    total = len(issues) + len(warnings) + len(passed)
    score = round((len(passed) / total) * 100) if total > 0 else 0
    return {
        'score': score,
        'issues': issues,
        'warnings': warnings,
        'passed': passed,
        'data': data,
    }
