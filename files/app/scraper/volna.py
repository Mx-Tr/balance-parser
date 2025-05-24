import asyncio, os, re, random
from datetime import datetime
from pathlib import Path
from configparser import ConfigParser

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

from app.db import Session, Balance
from dotenv import load_dotenv
load_dotenv()

# --------------------------------------------------------------------------- #
# Общие константы
# Если DEBUG=0, запускается без открывания окон браузера
HEADLESS = os.getenv("DEBUG", "0") != "1"

VOLNA_LOGIN_URL = (
    "https://sso.volnamobile.ru/volna-lk/auth?"
    "clientId=volna-auth&redirectURI=https%3a%2f%2fvolna-api-gw.volnamobile.ru"
    "%2fvolna-auth%2fapi%2fv1%2fauthorization%2fsuccess-login&responseType=code"
    "&responseMode=mode&scope=openid+profile&state=static&identityProviderId=VolnaIUA"
)

PHONE_INPUT  = "#phone"
PASS_INPUT   = "#pass"
SUBMIT_BTN   = 'button[type="submit"]'
BAL_SPAN = 'span[class*="balance-info_mainBalanceText"]'

STATE_DIR = Path(__file__).with_name("states")
STATE_DIR.mkdir(exist_ok=True)
# --------------------------------------------------------------------------- #

async def wait_balance(page, timeout=30_000) -> float:
    # Ждёт, пока скелетон исчезнет и в BAL_SPAN окажется финальный текст.
    # Возвращает balance как float (может быть и 0.0, если у аккаунта реально ноль).
    
    await page.wait_for_function(
        """
        (sel) => {
            const bal = document.querySelector(sel);
            if (!bal) return false;

            // Текст должен содержать хотя бы одну цифру
            if (!/\\d/.test(bal.textContent)) return false;

            // Проверяем, что ближайшего Skeleton-родителя с data-visible="true" нет
            let el = bal;
            while (el) {
                if (
                    el.classList?.contains('mantine-Skeleton-root') &&
                    el.getAttribute('data-visible') === 'true'
                ) return false;
                el = el.parentElement;
            }
            return true;    // скелетон ушёл, данные готовы
        }
        """,
        arg=BAL_SPAN,
        timeout=timeout,
    )

    raw = await page.inner_text(BAL_SPAN)
    return extract_balance(raw)

def load_accounts(ini_path: str = "accounts.ini") -> list[tuple[str, str]]:
    # Читает accounts.ini → [(login, password), …].
    cfg = ConfigParser()
    if not cfg.read(ini_path, encoding="utf-8"):
        raise FileNotFoundError(f"{ini_path} not found")

    accounts: list[tuple[str, str]] = [
        (cfg[s]["login"].strip(), cfg[s]["password"].strip())
        for s in cfg.sections()
        if cfg[s].get("login") and cfg[s].get("password")
    ]
    if not accounts:
        raise RuntimeError("Нет валидных учёток в accounts.ini")
    return accounts


async def login_flow(page, login: str, password: str) -> None:
    """Логин в ЛК Волны. Выходит сразу, если уже внутри."""
    await page.wait_for_load_state("networkidle")

    if await page.query_selector(BAL_SPAN):
        return

    await page.wait_for_selector(PHONE_INPUT, timeout=10_000)
    
    # удаляем +7 → берём последние 10 цифр
    phone_digits = re.sub(r"\D", "", login)[-10:]

    await page.click(PHONE_INPUT) # клик — чтобы фокус попал
    await page.fill(PHONE_INPUT, "") # очистка
    await page.type(PHONE_INPUT, phone_digits, delay=50) # по символу, как руками
    
    print(login, "заполнено")
    await page.fill(PASS_INPUT, password)

    btn = await page.query_selector(SUBMIT_BTN)
    if btn:
        await btn.click()
    else:
        await page.press(PASS_INPUT, "Enter")

    await page.wait_for_selector(BAL_SPAN, timeout=20_000)


def extract_balance(raw: str) -> float:
    num = re.sub(r"[^\d,\.]", "", raw)
    return float(num.replace(",", "."))


async def track_account(play, login: str, password: str) -> None:
    # Следит за балансом одного номера и пишет в БД.
    digits_only = re.sub(r"\D", "", login)
    state_file  = STATE_DIR / f"volna_{digits_only}.json"

    browser = await play.firefox.launch(headless=HEADLESS)
    context = await browser.new_context()  

    page = await context.new_page()
    await page.goto(VOLNA_LOGIN_URL, wait_until="domcontentloaded")
    await login_flow(page, login, password)

    while True:
        try:
            balance = await wait_balance(page) 

            with Session.begin() as s:
                s.merge(Balance(
                    id=f"volna_{digits_only}",
                    source="volna",
                    account=login,
                    value=balance,
                    updated_at=datetime.utcnow()
                ))
            print(f"✓ {datetime.now():%H:%M:%S}  {login}: {balance}")

            await context.storage_state(path=str(state_file))

        except PWTimeout:
            print(f"⚠️  {login}: timeout, пробую перелогин …")
            try:
                await login_flow(page, login, password)
            except Exception as e:
                print(f"❌  {login}: не вошёл ({e})")

        await asyncio.sleep(random.randint(55, 65))
        await page.reload(wait_until="domcontentloaded")


async def main() -> None:
    accounts = load_accounts()
    print(f"Стартуем {len(accounts)} аккаунт(ов)…")

    async with async_playwright() as p:
        tasks = [asyncio.create_task(track_account(p, login, pwd))
                 for login, pwd in accounts]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Остановлено по Ctrl+C")
    except Exception as e:
        import traceback, sys
        print("‼Непойманное исключение:", e, file=sys.stderr)
        traceback.print_exc()
        input("\nНажмите Enter, чтобы закрыть окно")
