import os
import time
import threading
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException,
    ElementClickInterceptedException,
    TimeoutException,
)
from core.settings import get_settings
from core.constants import ALLOWED_RELATORIES, ALLOWED_ITEM_TYPES, GEOGRID_URL

settings = get_settings()

GEOGRID_USER = settings.GEOGRID_USER
GEOGRID_PASS = settings.GEOGRID_PASSWORD

export_lock = threading.Lock()

# In-memory status store, keyed by relatory name.
# Fine for a single-process app with one export at a time (export_lock);
# TODO: Use regis insted of a dict
export_status = {}

def set_status(relatory: str, step: str, status: str = "processing"):
    export_status[relatory] = {"step": step, "status": status}

def click(driver, by, value, timeout=15, retries=20, retry_delay=1):
    last_error = None
    for attempt in range(retries):
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((by, value))
            )
            if attempt < retries - 1:
                element.click()
            else:
                # Last attempt: force click via JS
                driver.execute_script("arguments[0].click();", element)
            return element
        except (StaleElementReferenceException, ElementClickInterceptedException, TimeoutException) as error:
            last_error = error
            time.sleep(retry_delay)
    raise last_error


def export_relatory(relatory: str, download_dir: str = None):
    if relatory not in ALLOWED_RELATORIES:
        raise RuntimeError("This relatory doesn't have support yet, try a valid one")

    if download_dir is None:
        PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        download_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(download_dir, exist_ok=True)

    options = Options()
    options.add_argument("--headless=new")
    options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
    })

    driver = webdriver.Chrome(options=options)

    try:
    # In headless mode, downloads are automatically blocked, even with
    # download.default_directory set in options.
    # So we use the Chrome DevTools Protocol to force downloads and set where they go.
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": download_dir,
        })

        driver.get(GEOGRID_URL)

        # LOGIN
        set_status(relatory, step="login")
        user_box = driver.find_element(by=By.NAME, value="usuario")
        user_box.send_keys(GEOGRID_USER)

        password_box = driver.find_element(by=By.NAME, value="senha")
        password_box.send_keys(GEOGRID_PASS)

        # Cookie/terms banner doesn't always appear, so only click if it exists
        cookies_button = driver.find_elements(by=By.NAME, value="aceitar")
        if cookies_button:
            click(driver, By.NAME, "aceitar")

        click(driver, By.NAME, "entrar")

        # RELATORY SELECT
        click(driver, By.CLASS_NAME, "elemento-menu")
        click(driver, By.NAME, "relatorios")
        click(driver, By.CSS_SELECTOR, f"div[data-relatorio='{relatory}']")

        # COLUMNS IN THE XLSX
        set_status(relatory, step="configurando colunas")
        click(driver, By.NAME, "configurar")
        if relatory in ALLOWED_ITEM_TYPES:
            click(driver, By.XPATH, "//label[.//span[text()='Tipo']]//input[@name='item']")
        click(driver, By.XPATH, "//label[.//span[text()='Usuário']]//input[@name='item']")
        click(driver, By.NAME, "salvar")

        # FILTER - exclude records that are still just a project (not executed yet)
        # Not every relatory type exposes an "Execução" filter, so only click it if present.
        set_status(relatory, step="filtrando dados")
        click(driver, By.NAME, "adicionar-filtros")
        execucao_xpath = "//label[.//span[text()='Execução']]//input[@name='item']"
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, execucao_xpath))
            )
            click(driver, By.XPATH, execucao_xpath)
        except TimeoutException:
            pass
        click(driver, By.XPATH, "//button[@name='salvar' and normalize-space(text())='Aplicar filtros']")

        # EXCEL
        set_status(relatory, step="Exportando")
        click(driver, By.NAME, "exportar-xls")
        archive_name = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "div[name='titulo'] input"))
        )
        archive_name.clear()
        archive_name.send_keys(relatory)
        click(driver, By.XPATH, "//button[@name='salvar' and normalize-space(text())='Exportar']")

        # Wait 2 minutes before ending the script, so it has time to download bigger relatories
        time.sleep(120)
    finally:
        set_status(relatory, step="Concluido", status="Done")
        driver.quit()
        
def run_export(relatory : str):
    with export_lock:
        export_relatory(relatory)

       
def treat_viabilidade():
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    data_dir = os.path.join(PROJECT_ROOT, "data")
    file_path = os.path.join(data_dir, "viabilidade.xlsx")

    if not os.path.isfile(file_path):
        return None
    
    raw_df = pd.read_excel(file_path)
    
    mask_cto = raw_df["Tipo"].str.contains("CTO", case=False, na=False)

    cto_df = raw_df[mask_cto].copy()
    ceo_df = raw_df[~mask_cto].copy()

    cols_numericas = [
        "Quantidade equip.", "Quantidade portas", "Portas ocupadas",
        "Portas livres", "Portas atendimento cliente",
    ]
    cto_df = cto_df.dropna(subset=cols_numericas, how="all")
    cto_df[cols_numericas] = cto_df[cols_numericas].fillna(0)

    cols_tabela = ["Sigla", "Latitude", "Longitude", "Cidade"] + cols_numericas
    cto_table = cto_df[cols_tabela].copy().fillna("")

    ceo_df = ceo_df.dropna(subset=cols_numericas, how="all")
    ceo_df[cols_numericas] = ceo_df[cols_numericas].fillna(0)
    ceo_table = ceo_df[cols_tabela].copy().fillna("")

    estatisticas = {
        "Equipamentos": int(cto_table["Quantidade equip."].sum()),
        "Portas": int(cto_table["Quantidade portas"].sum()),
        "Portas ocupadas": int(cto_table["Portas ocupadas"].sum()),
        "Portas livres": int(cto_table["Portas livres"].sum()),
        "Portas atendimento cliente": int(cto_table["Portas atendimento cliente"].sum()),
    }

    return {
        "estatisticas": estatisticas,
        "dataframe": cto_table.to_dict(orient="records"),
        "ceo": ceo_table.to_dict(orient="records"),
    }
