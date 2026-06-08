"""XHS QR code login — pure HTTP mode (no browser)"""
import sys
import json
import time
sys.stdout.reconfigure(encoding='utf-8')

from xhs_cli.client import XhsClient
from xhs_cli.qr_login import _generate_a1, _generate_webid, _apply_session_cookies, _build_saved_cookies, _complete_confirmed_session, _resolved_user_id, save_cookies, _display_qr_in_terminal


QR_SCANNED = 1
QR_CONFIRMED = 2
POLL_INTERVAL_S = 2


def main():
    print("=" * 50)
    print("  小红书 QR 码登录 (纯 HTTP)")
    print("  请用小红书 App 扫描二维码")
    print("=" * 50)
    print(flush=True)

    a1 = _generate_a1()
    webid = _generate_webid()
    tmp_cookies = {"a1": a1, "webId": webid}
    print(f"Generated a1: {a1[:20]}...", flush=True)

    with XhsClient(tmp_cookies, request_delay=0) as client:
        # Step 1: Activate session
        print("Step 1: Activating session...", flush=True)
        try:
            activate_data = client.login_activate()
            _apply_session_cookies(client, activate_data)
            print(f"  Session activated: {activate_data.get('session', '')[:20]}...", flush=True)
        except Exception as exc:
            print(f"  Activate warning (non-fatal): {exc}", flush=True)

        # Step 2: Create QR code
        print("Step 2: Creating QR code...", flush=True)
        qr_data = client.create_qr_login()
        qr_id = qr_data["qr_id"]
        code = qr_data["code"]
        qr_url = qr_data["url"]
        print(f"  QR ID: {qr_id}", flush=True)
        print(f"  QR URL: {qr_url}", flush=True)
        print(flush=True)

        # Display QR in terminal
        print("请用小红书 App 扫描以下二维码:", flush=True)
        if not _display_qr_in_terminal(qr_url):
            print(f"  [无法渲染二维码] 请手动访问: {qr_url}", flush=True)
        print(flush=True)

        # Step 3: Poll for scan result
        print("等待扫码... (120秒超时)", flush=True)
        start = time.time()
        timeout_s = 120

        while (time.time() - start) < timeout_s:
            time.sleep(POLL_INTERVAL_S)
            elapsed = int(time.time() - start)

            try:
                status_data = client.check_qr_status(qr_id, code)
            except Exception as exc:
                print(f"  [{elapsed}s] Poll error: {exc}", flush=True)
                continue

            code_status = status_data.get("codeStatus", -1)

            if code_status == QR_SCANNED:
                print(f"  [{elapsed}s] 已扫码! 等待确认...", flush=True)
            elif code_status == QR_CONFIRMED:
                print(f"  [{elapsed}s] 登录确认!", flush=True)

                confirmed_user_id = status_data.get("userId", "")
                completion_data = _complete_confirmed_session(
                    client, qr_id, code, confirmed_user_id
                )
                user_id = _resolved_user_id(completion_data) or confirmed_user_id
                cookies = _build_saved_cookies(a1, webid, client.cookies)
                save_cookies(cookies)

                # Save to local file
                cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
                with open("xhs_cookies.json", "w", encoding="utf-8") as f:
                    json.dump(cookies, f, ensure_ascii=False, indent=2)

                print(f"\n登录成功! User ID: {user_id}", flush=True)
                print(f"Cookie saved to xhs_cookies.json", flush=True)
                return

            if elapsed % 15 == 0 and elapsed > 0:
                print(f"  [{elapsed}s] 仍在等待...", flush=True)

        print("\n超时! 请重新运行脚本。", flush=True)


if __name__ == "__main__":
    main()
