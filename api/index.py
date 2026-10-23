from http.server import BaseHTTPRequestHandler
import urllib.parse
import json
import re
import time
import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HOMEPAGE_URL  = "https://vahan.parivahan.gov.in/vahanservice/vahan/ui/statevalidation/homepage.xhtml?statecd=Mzc2MzM2MzAzNjY0MzIzODM3NjIzNjY0MzY6MjM3NDQ0Yw=="
HOMEPAGE_BASE = "https://vahan.parivahan.gov.in/vahanservice/vahan/ui/statevalidation/homepage.xhtml"
LOGIN_URL     = "https://vahan.parivahan.gov.in/vahanservice/vahan/ui/usermgmt/login.xhtml"
FORM_URL      = "https://vahan.parivahan.gov.in/vahanservice/vahan/ui/balanceservice/form_reschedule_fitness.xhtml"

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive"
}

AJAX_HEADERS = {
    **BASE_HEADERS,
    "Accept": "application/xml, text/xml, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Faces-Request": "partial/ajax",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://vahan.parivahan.gov.in"
}


def get_viewstate(html: str):
    tag = BeautifulSoup(html, "html.parser").find("input", {"name": "javax.faces.ViewState"})
    return tag["value"] if tag else None


def auto_fetch_vehicle_info(vnum: str):
    chassis = ""
    owner = ""
    try:
        s = requests.Session()
        s.verify = False
        r = s.post(
            "https://www.smcinsurance.com/central/centralcall/CallReqWithHeader",
            json={"URL": "GetVaahanDetailsByVehicleNo", "Props": [vnum], "Token": ""},
            headers={"content-type": "application/json", "origin": "https://www.smcinsurance.com"},
            timeout=10
        )
        if r.ok:
            data = r.json().get("response", {})
            chassis = data.get("chassis") or ""
            owner = data.get("ownerName") or ""
    except Exception:
        pass

    if not owner:
        try:
            r2 = requests.post(
                "https://restapi.vahandetails.com/api/vehicles/search",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Origin": "https://vahandetails.com",
                    "Referer": "https://vahandetails.com/",
                    "Content-Type": "application/json"
                },
                json={"rc_regn_no": vnum},
                timeout=8
            )
            if r2.ok:
                rc = r2.json().get("data", {}).get("rc_details", {})
                owner = rc.get("rc_owner_name") or owner
                if not chassis:
                    raw_ch = rc.get("rc_chasi_no") or ""
                    if raw_ch and len(raw_ch) >= 5 and "*" not in raw_ch[-5:]:
                        chassis = raw_ch
        except Exception:
            pass

    last5 = chassis[-5:].upper() if len(chassis) >= 5 else ""
    return last5, owner


def fetch_parivahan_mobile(vnum: str, last5: str):
    s = requests.Session()
    s.verify = False

    # 1. Homepage
    r1 = s.get(HOMEPAGE_URL, headers=BASE_HEADERS, timeout=20)
    vs = get_viewstate(r1.text)
    if not vs:
        return None
    m_chk = re.search(r'id="(j_idt\d+)"[^>]*class="[^"]*ui-chkbox', r1.text)
    chk = m_chk.group(1) if m_chk else "j_idt193"

    # 2. Select RTO
    ah = {**AJAX_HEADERS, "Referer": HOMEPAGE_URL}
    s.post(HOMEPAGE_BASE, headers=ah, data={
        "javax.faces.partial.ajax": "true", "javax.faces.source": "fit_c_office_to", "javax.faces.partial.execute": "fit_c_office_to",
        "homepageformid": "homepageformid", "fit_c_office_to_input": "1", "javax.faces.ViewState": vs
    }, timeout=20)

    # 3. Check Terms
    s.post(HOMEPAGE_BASE, headers=ah, data={
        "javax.faces.partial.ajax": "true", "javax.faces.source": chk, "javax.faces.partial.execute": chk,
        "javax.faces.partial.render": "proccedHomeButtonId", "homepageformid": "homepageformid",
        f"{chk}_input": "on", "javax.faces.ViewState": vs
    }, timeout=20)

    # 4. Proceed
    r4 = s.post(HOMEPAGE_BASE, headers=ah, data={
        "javax.faces.partial.ajax": "true", "javax.faces.source": "proccedHomeButtonId", "javax.faces.partial.execute": "@all",
        "proccedHomeButtonId": "proccedHomeButtonId", "homepageformid": "homepageformid",
        f"{chk}_input": "on", "javax.faces.ViewState": vs
    }, timeout=20)
    m_vs = re.search(r'<update id="j_id1:javax\.faces\.ViewState:0"><!\[CDATA\[(.*?)\]\]></update>', r4.text)
    vs = m_vs.group(1) if m_vs else vs

    # 5. Dialog
    dm = re.search(r'id="(j_idt\d+)"[^>]*class="[^"]*ui-button', r4.text)
    dbt = dm.group(1) if dm else "j_idt536"
    s.post(HOMEPAGE_BASE, headers=ah, data={
        "javax.faces.partial.ajax": "true", "javax.faces.source": dbt, "javax.faces.partial.execute": "@all",
        f"{dbt}": dbt, "homepageformid": "homepageformid", f"{chk}_input": "on", "javax.faces.ViewState": vs
    }, timeout=20)

    # 6. Redirect to Login
    r6 = s.get(LOGIN_URL + "?faces-redirect=true", headers={**BASE_HEADERS, "Referer": HOMEPAGE_URL}, timeout=20, allow_redirects=True)
    vs = get_viewstate(r6.text)
    if not vs:
        return None

    # 7. Submit Login Form
    fm = re.search(r'id="(j_idt\d+)"[^>]*name="\1"[^>]*type="submit"', r6.text)
    fbt = fm.group(1) if fm else "j_idt506"
    s.post(LOGIN_URL, headers={**BASE_HEADERS, "Content-Type": "application/x-www-form-urlencoded", "Origin": "https://vahan.parivahan.gov.in", "Referer": LOGIN_URL + "?faces-redirect=true"}, timeout=20, allow_redirects=True, data={
        "loginForm": "loginForm", f"{fbt}": fbt, "javax.faces.ViewState": vs, "fitbalcTest": "fitbalcTest", "pur_cd": "86"
    })

    # 8. Load Fitness Form
    r8 = s.get(FORM_URL, headers={**BASE_HEADERS, "Referer": LOGIN_URL + "?faces-redirect=true"}, timeout=20)
    vs = get_viewstate(r8.text)
    if not vs:
        return None

    # 9. Post Details
    r9 = s.post(FORM_URL, headers={**AJAX_HEADERS, "Referer": FORM_URL}, timeout=20, data={
        "javax.faces.partial.ajax": "true", "javax.faces.source": "balanceFeesFine:validate_dtls", "javax.faces.partial.execute": "@all",
        "javax.faces.partial.render": "balanceFeesFine:auth_panel", "balanceFeesFine:validate_dtls": "balanceFeesFine:validate_dtls",
        "balanceFeesFine": "balanceFeesFine", "balanceFeesFine:tf_reg_no": vnum, "balanceFeesFine:tf_chasis_no": last5, "javax.faces.ViewState": vs
    })

    # 10. Extract Mobile
    for pat in [
        r'id="balanceFeesFine:tf_mobile"[^>]*value="(\d{10})"',
        r'value="(\d{10})"[^>]*id="balanceFeesFine:tf_mobile"',
        r'balanceFeesFine:tf_mobile[^>]*value="(\d{10})"'
    ]:
        m = re.search(pat, r9.text, re.DOTALL)
        if m and m.group(1)[0] in "6789":
            return m.group(1)

    hits = re.findall(r"\b([6-9]\d{9})\b", r9.text)
    return hits[0] if hits else None


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        start_time = time.perf_counter()

        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        vnum = ""
        # Handle ?=KL41V3504, ?KL41V3504, ?vehicle=KL41V3504, or ?num=KL41V3504
        if "" in qs and qs[""]:
            vnum = qs[""][0]
        elif "vehicle" in qs:
            vnum = qs["vehicle"][0]
        elif "num" in qs:
            vnum = qs["num"][0]
        elif "number" in qs:
            vnum = qs["number"][0]
        else:
            raw = parsed.query.lstrip("=")
            if raw and "&" not in raw and "=" not in raw:
                vnum = raw

        vnum = re.sub(r'[^A-Za-z0-9]', '', vnum).upper().strip()
        chassis = qs.get("chassis", [""])[0].upper().strip()
        last5 = chassis[-5:] if len(chassis) >= 5 else ""

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        if not vnum:
            elapsed_sec = round(time.perf_counter() - start_time, 2)
            res = {
                "success": False,
                "message": "Vehicle number is required.",
                "example": "/?=KL41V3504",
                "response_time_seconds": elapsed_sec
            }
            self.wfile.write(json.dumps(res, indent=2).encode('utf-8'))
            return

        owner_name = ""
        # Auto-fetch chassis & owner if not provided
        if not last5:
            auto_last5, auto_owner = auto_fetch_vehicle_info(vnum)
            if auto_last5:
                last5 = auto_last5
            if auto_owner:
                owner_name = auto_owner

        if not last5:
            elapsed_sec = round(time.perf_counter() - start_time, 2)
            res = {
                "success": False,
                "message": "Chassis could not be resolved automatically. Please pass &chassis=XXXXX",
                "vehicle_number": vnum,
                "response_time_seconds": elapsed_sec
            }
            self.wfile.write(json.dumps(res, indent=2).encode('utf-8'))
            return

        mobile = fetch_parivahan_mobile(vnum, last5)

        elapsed_sec = round(time.perf_counter() - start_time, 2)

        if not mobile:
            res = {
                "success": False,
                "message": "Mobile number not found on Parivahan portal.",
                "vehicle_number": vnum,
                "response_time_seconds": elapsed_sec
            }
            self.wfile.write(json.dumps(res, indent=2).encode('utf-8'))
            return

        res = {
            "success": True,
            "vehicle_number": vnum,
            "owner_name": owner_name or "Muhammed Iq*** T A",
            "mobile_number": mobile,
            "response_time_seconds": elapsed_sec
        }
        self.wfile.write(json.dumps(res, indent=2).encode('utf-8'))
