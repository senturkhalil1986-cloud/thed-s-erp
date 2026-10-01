import streamlit as st
import pandas as pd
from datetime import datetime
import os
from PIL import Image
from io import BytesIO

# --- GÜVENLİ GİRİŞ / KULLANICI YÖNETİMİ ---
import sqlite3
import hashlib
import hmac
import secrets
import tempfile
import threading
import logging
import json

st.set_page_config(page_title="THE DIŞ TİCARET - ERP", page_icon="🏭", layout="wide")

DB_DIR = "data"
os.makedirs(DB_DIR, exist_ok=True)
AUTH_DB = os.path.join(DB_DIR, "users.sqlite3")
DATA_LOCK = threading.RLock()
logging.basicConfig(filename=os.path.join(DB_DIR, "erp.log"), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

def auth_conn():
    conn = sqlite3.connect(AUTH_DB, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, salt BLOB NOT NULL, password_hash BLOB NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL)")
    conn.commit()
    return conn

def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310000)

def init_audit_table():
    with auth_conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT
        )""")
        conn.commit()

def _json_safe(value):
    if value is None:
        return None
    if isinstance(value, pd.DataFrame):
        value = value.to_dict(orient="records")
    elif isinstance(value, pd.Series):
        value = value.to_dict()
    return json.dumps(value, ensure_ascii=False, default=str)

def audit_log(action, entity_type, entity_id, old_value=None, new_value=None):
    init_audit_table()
    with auth_conn() as conn:
        conn.execute(
            "INSERT INTO audit_log(created_at,username,action,entity_type,entity_id,old_value,new_value) VALUES(?,?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), st.session_state.get("username", "system"),
             action, entity_type, str(entity_id), _json_safe(old_value), _json_safe(new_value))
        )
        conn.commit()

def load_audit_log(limit=1000):
    init_audit_table()
    with auth_conn() as conn:
        return pd.read_sql_query(
            "SELECT id,created_at,username,action,entity_type,entity_id,old_value,new_value FROM audit_log ORDER BY id DESC LIMIT ?",
            conn, params=(limit,)
        )

def create_user(username, password, role="personel"):
    username = username.strip()
    if not username or len(password) < 12:
        raise ValueError("Kullanıcı adı zorunlu; şifre en az 12 karakter olmalı.")
    salt = secrets.token_bytes(16)
    with auth_conn() as conn:
        conn.execute("INSERT INTO users(username,salt,password_hash,role,active,created_at) VALUES(?,?,?,?,1,?)",
                     (username, salt, password_hash(password, salt), role, datetime.now().isoformat(timespec="seconds")))

def user_count():
    with auth_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

def authenticate(username, password):
    with auth_conn() as conn:
        row = conn.execute("SELECT salt,password_hash,role,active FROM users WHERE username=?", (username.strip(),)).fetchone()
    if not row or not row[3]:
        return None
    return row[2] if hmac.compare_digest(password_hash(password, row[0]), row[1]) else None

def check_password():
    if user_count() == 0:
        st.subheader("🔐 İlk Kurulum — Yönetici Hesabı")
        st.info("İlk açılışta yönetici hesabı oluştur. Şifren en az 12 karakter olmalı.")
        with st.form("initial_admin_form"):
            username = st.text_input("Yönetici kullanıcı adı", value="admin")
            password = st.text_input("Yönetici şifresi", type="password")
            confirm = st.text_input("Şifreyi tekrar gir", type="password")
            submitted = st.form_submit_button("Yönetici Hesabını Oluştur")
        if submitted:
            if password != confirm:
                st.error("Şifreler eşleşmiyor.")
            else:
                try:
                    create_user(username, password, "admin")
                    st.success("Yönetici hesabı oluşturuldu. Şimdi giriş yapabilirsin.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hesap oluşturulamadı: {exc}")
        return False
    if not st.session_state.get("authenticated", False):
        st.subheader("🔐 THE DIŞ TİCARET - ERP Giriş Paneli")
        with st.form("login_form"):
            username = st.text_input("Kullanıcı adı")
            password = st.text_input("Şifre", type="password")
            submitted = st.form_submit_button("Giriş Yap")
        if submitted:
            role = authenticate(username, password)
            if role:
                st.session_state.update(authenticated=True, username=username.strip(), role=role)
                logging.info("LOGIN user=%s", username.strip())
                st.rerun()
            st.error("Kullanıcı adı veya şifre hatalı; hesap pasif olabilir.")
        return False
    return True

if not check_password():
    st.stop()

# --- BURADAN SONRASI ERP KODLARIN ---


DB_DIR = "data"
PHOTO_DIR = os.path.join(DB_DIR, "production_photos")
SHIPMENT_PHOTO_DIR = os.path.join(DB_DIR, "shipment_photos")
SHIPMENT_DOC_DIR = os.path.join(DB_DIR, "shipment_docs")
SPEC_FILE_DIR = os.path.join(DB_DIR, "spec_files")
SPEC_PHOTO_DIR = os.path.join(DB_DIR, "spec_photos")

os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(PHOTO_DIR, exist_ok=True)
os.makedirs(SHIPMENT_PHOTO_DIR, exist_ok=True)
os.makedirs(SHIPMENT_DOC_DIR, exist_ok=True)
os.makedirs(SPEC_FILE_DIR, exist_ok=True)
os.makedirs(SPEC_PHOTO_DIR, exist_ok=True)

MASTER_ITEMS_FILE = os.path.join(DB_DIR, "master_items.csv")
STOCK_TRANSACTIONS_FILE = os.path.join(DB_DIR, "stock_transactions.csv")
PRODUCTION_META_FILE = os.path.join(DB_DIR, "production_meta.csv")
SHIPMENT_META_FILE = os.path.join(DB_DIR, "shipment_meta.csv")
CARILER_FILE = os.path.join(DB_DIR, "cariler.csv")
SPEK_FILE = os.path.join(DB_DIR, "cari_urun_spekleri.csv")

def load_data(filepath, columns):
    if os.path.exists(filepath):
        try:
            df = pd.read_csv(filepath)
            for col in columns:
                if col not in df.columns:
                    df[col] = ""
            if "StokKodu" in df.columns:
                df = df.dropna(subset=["StokKodu"])
                df = df[df["StokKodu"].astype(str).str.strip() != ""]
                df = df[df["StokKodu"].astype(str).str.lower() != "bilinmiyor"]
            return df
        except Exception as exc:
            # Bozuk dosyayı boş tablo gibi göstermeyiz; yanlışlıkla üzerine yazılmasını önleriz.
            logging.exception("DATA_READ_ERROR file=%s", filepath)
            raise RuntimeError(f"Veri dosyası okunamadı: {filepath}. Dosya korunuyor; yedekten kontrol edin.") from exc
    return pd.DataFrame(columns=columns)

def save_data(df, filepath):
    """CSV'yi aynı dizinde geçici dosyaya yazıp atomik olarak değiştirir."""
    directory = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(directory, exist_ok=True)
    with DATA_LOCK:
        # Günlük ilk değişiklikten önce dosyanın bir kopyasını sakla.
        if os.path.exists(filepath):
            backup_dir = os.path.join(DB_DIR, "backups", datetime.now().strftime("%Y-%m-%d"))
            os.makedirs(backup_dir, exist_ok=True)
            backup_path = os.path.join(backup_dir, os.path.basename(filepath) + ".bak")
            if not os.path.exists(backup_path):
                import shutil
                shutil.copy2(filepath, backup_path)
        fd, tmp_path = tempfile.mkstemp(prefix=".erp_", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as handle:
                df.to_csv(handle, index=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, filepath)
            logging.info("DATA_SAVE user=%s file=%s rows=%s", st.session_state.get("username","system"), os.path.basename(filepath), len(df))
        except Exception:
            try: os.unlink(tmp_path)
            except OSError: pass
            raise

st.title("THE DIŞ TİCARET - ERP Stok and Üretim Yönetim Sistemi")

menu = [
    "1. Stok Kartı Tanımlama", 
    "2. Depo / Malzeme Girişi", 
    "3. Cari dan Ürün Spek Yönetimi",
    "4. Üretime Sevk / Reçeteli Üretim and Maliyet",
    "5. Stok Durumu, Hareket Panosu and Föy Düzenleme",
    "6. Sevkiyat & Çıkış Yönetimi (İlçe Tarım & Foto)",
    "7. İzlenebilirlik & İşlem Geçmişi"
]
choice = st.sidebar.radio("📋 ERP Modülleri", menu)

st.sidebar.markdown("---")
st.sidebar.caption(f"Oturum: {st.session_state.get('username','')} ({st.session_state.get('role','')})")
if st.sidebar.button("Çıkış Yap"):
    logging.info("LOGOUT user=%s", st.session_state.get("username",""))
    for key in ("authenticated", "username", "role"):
        st.session_state.pop(key, None)
    st.rerun()

if st.session_state.get("role") == "admin":
    with st.sidebar.expander("👥 Kullanıcı Yönetimi"):
        with st.form("add_user_form", clear_on_submit=True):
            new_username = st.text_input("Yeni kullanıcı adı")
            new_password = st.text_input("Geçici/ilk şifre (min. 12 karakter)", type="password")
            new_role = st.selectbox("Rol", ["personel", "admin"])
            add_user = st.form_submit_button("Kullanıcı Oluştur")
        if add_user:
            try:
                create_user(new_username, new_password, new_role)
                logging.info("USER_CREATE by=%s user=%s role=%s", st.session_state.get("username"), new_username.strip(), new_role)
                st.success("Kullanıcı oluşturuldu.")
            except sqlite3.IntegrityError:
                st.error("Bu kullanıcı adı zaten kayıtlı.")
            except Exception as exc:
                st.error(str(exc))
    with st.sidebar.expander("⚠️ Tehlikeli işlemler"):
        confirm_reset = st.checkbox("Tüm CSV verilerini silmeyi onaylıyorum")
        if st.button("Tüm Verileri Sıfırla", disabled=not confirm_reset):
            for f_path in [MASTER_ITEMS_FILE, STOCK_TRANSACTIONS_FILE, PRODUCTION_META_FILE, SHIPMENT_META_FILE, CARILER_FILE, SPEK_FILE]:
                if os.path.exists(f_path): os.remove(f_path)
            logging.warning("DATA_RESET by=%s", st.session_state.get("username"))
            st.success("CSV verileri silindi.")
            st.rerun()

# --- 1. STOK KARTI TANIMLAMA ---
if choice == "1. Stok Kartı Tanımlama":
    st.header("🗂️ Yeni Stok Kartı Tanımlama ve Yönetimi")
    
    with st.form("new_stock_card", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            s_code = st.text_input("Stok Kodu (Örn: HMM-01, AMB-01, MAM-01)")
            s_name = st.text_input("Stok Adı / Cinsi (Örn: 3000 ml Pet Jalapeno Turşusu)")
        with col2:
            s_depot = st.selectbox("Varsayılan Depo", [
                "Soğuk Hava Deposu", 
                "Yardımcı Malzeme Deposu", 
                "Yarı Mamül Deposu", 
                "Mamül Deposu"
            ])
            s_unit = st.selectbox("Stok Birimi", ["Kg", "Adet", "Ton", "Koli", "Metre"])
            
        submitted = st.form_submit_button("Stok Kartını Kaydet")
        if submitted:
            if not s_code.strip() or not s_name.strip():
                st.error("Stok kodu and stok adı zorunludur!")
            else:
                df_master = load_data(MASTER_ITEMS_FILE, ["StokKodu", "StokAdi", "Depo", "Birim"])
                if not df_master.empty and s_code.strip() in df_master["StokKodu"].astype(str).values:
                    st.error(f"'{s_code}' stok kodu zaten sistemde kayıtlı!")
                else:
                    new_row = pd.DataFrame([{
                        "StokKodu": s_code.strip(),
                        "StokAdi": s_name.strip(),
                        "Depo": s_depot,
                        "Birim": s_unit
                    }])
                    df_master = pd.concat([df_master, new_row], ignore_index=True)
                    save_data(df_master, MASTER_ITEMS_FILE)
                    st.success(f"'{s_name.strip()}' ({s_code.strip()}) stok kartı başarıyla açıldı!")

    st.subheader("📋 Sistemde Tanımlı Stok Kartları ve Silme")
    master_df = load_data(MASTER_ITEMS_FILE, ["StokKodu", "StokAdi", "Depo", "Birim"])
    if master_df.empty:
        st.info("Henüz sistemde hiç stok kartı yok.")
    else:
        st.dataframe(master_df, use_container_width=True)
        
        st.markdown("### 🗑️ Yanlış Girilen Stok Kartını Sil")
        stok_secenekleri = [f"{row['StokKodu']} - {row['StokAdi']}" for _, row in master_df.iterrows()]
        secilen_stok_sil = st.selectbox("Silmek İstediğin Stok Kartını Seç", ["Seçiniz..."] + stok_secenekleri)
        if st.button("Seçilen Stok Kartını Sil"):
            if secilen_stok_sil != "Seçiniz...":
                silinecek_kod = secilen_stok_sil.split(" - ")[0].strip()
                tx_check = load_data(STOCK_TRANSACTIONS_FILE, ["StokKodu"])
                if not tx_check.empty and silinecek_kod in tx_check["StokKodu"].astype(str).values:
                    st.error(f"🚨 '{silinecek_kod}' kodlu ürün için daha önce depo/stok hareketi yapılmış! Önce ilgili hareketleri silmelisiniz.")
                else:
                    master_df = master_df[master_df["StokKodu"].astype(str) != silinecek_kod]
                    save_data(master_df, MASTER_ITEMS_FILE)
                    st.success(f"'{silinecek_kod}' stok kartı silindi!")
                    st.rerun()

# --- 2. DEPO / MALZEME GİRİŞİ ---
elif choice == "2. Depo / Malzeme Girişi":
    st.header("📥 Depo Malzeme Kabul (Giriş Fişi) ve Yönetimi")
    
    master_df = load_data(MASTER_ITEMS_FILE, ["StokKodu", "StokAdi", "Depo", "Birim"])
    
    if master_df.empty:
        st.error("🚨 Sistemde tanımlı stok kartı yok! Önce '1. Stok Kartı Tanımlama' modülünden kart açmalısın.")
    else:
        item_options = [row['StokAdi'] for _, row in master_df.iterrows()]
        
        selected_item_str = st.selectbox("Ürün Seçimi", item_options, key="stock_in_item_select")
        selected_item_row = master_df[master_df["StokAdi"] == selected_item_str].iloc[0]
        default_depo = selected_item_row["Depo"]

        with st.form("stock_in_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                g_tarih = st.date_input("Giriş Tarihi", datetime.now())
                
                st.markdown(f"**Malzemenin Gireceği Depo (Stok Kartı Tanımlı):**")
                hedef_depo = st.text_input("Hedef Depo", value=default_depo, disabled=True, label_visibility="collapsed")
                
                miktar = st.number_input("Giriş Miktarı", min_value=0.01, step=1.0, format="%.2f")
            with col2:
                birim_fiyat = st.number_input("Birim Fiyat (TL) *Zorunlu*", min_value=0.01, step=0.01, value=1.0, format="%.2f")
                parti_no = st.text_input("Parti / Lot Numarası *Zorunlu and Benzersiz Olmalı*")
                tedarikci = st.text_input("Tedarikçi / Cari Firma Adı")
                irsaliye_no = st.text_input("İrsaliye / Fatura No")

            submitted = st.form_submit_button("Depoya Girişi Onayla")
            if submitted:
                if not parti_no.strip():
                    st.error("Parti / Lot numarası zorunludur!")
                elif birim_fiyat <= 0:
                    st.error("Birim fiyat sıfırdan büyük olmalıdır!")
                elif miktar <= 0:
                    st.error("Miktar sıfırdan büyük olmalıdır!")
                else:
                    tx_check_df = load_data(STOCK_TRANSACTIONS_FILE, ["PartiNo"])
                    existing_parties = []
                    if not tx_check_df.empty and "PartiNo" in tx_check_df.columns:
                        existing_parties = tx_check_df["PartiNo"].astype(str).str.strip().values

                    if parti_no.strip() in existing_parties:
                        st.error(f"🚨 Hata: '{parti_no.strip()}' parti/lot numarası sistemde zaten kayıtlı!")
                    else:
                        new_tx = pd.DataFrame([{
                            "Tarih": str(g_tarih),
                            "HareketTuru": "Giriş",
                            "Depo": default_depo,
                            "StokKodu": selected_item_row["StokKodu"],
                            "StokAdi": selected_item_row["StokAdi"],
                            "Birim": selected_item_row["Birim"],
                            "Miktar": miktar,
                            "BirimFiyat": birim_fiyat,
                            "ToplamTutar": miktar * birim_fiyat,
                            "PartiNo": parti_no.strip(),
                            "Tedarikci": tedarikci.strip(),
                            "Aciklama": f"İrsaliye: {irsaliye_no.strip()}"
                        }])
                        
                        tx_df = load_data(STOCK_TRANSACTIONS_FILE, new_tx.columns.tolist())
                        tx_df = pd.concat([tx_df, new_tx], ignore_index=True)
                        save_data(tx_df, STOCK_TRANSACTIONS_FILE)
                        audit_log("OLUŞTURMA", "DEPO_GIRISI", parti_no.strip(), new_value=new_tx)
                        st.success(f"Depo girişi başarıyla işlendi! ({default_depo} - Parti No: {parti_no})")

    st.subheader("📑 Son Yapılan Depo Giriş Hareketleri ve Silme")
    tx_history = load_data(STOCK_TRANSACTIONS_FILE, ["Tarih", "HareketTuru", "Depo", "StokKodu", "StokAdi", "Birim", "Miktar", "BirimFiyat", "ToplamTutar", "PartiNo", "Tedarikci", "Aciklama"])
    if tx_history.empty or tx_history[tx_history["HareketTuru"] == "Giriş"].empty:
        st.info("Henüz depo girişi bulunmuyor.")
    else:
        giris_df = tx_history[tx_history["HareketTuru"] == "Giriş"].copy()
        styled_giris = giris_df.style.format({
            "Miktar": "{:,.2f}",
            "BirimFiyat": "{:,.2f} TL",
            "ToplamTutar": "{:,.2f} TL"
        }, na_rep="")
        st.dataframe(styled_giris, use_container_width=True)
        
        st.markdown("### 🗑️ Yanlış Girilen Depo Giriş Fişini / Lotunu Sil")
        giris_secenekleri = [f"Parti: {row['PartiNo']} | {row['StokAdi']} | Miktar: {row['Miktar']} {row['Birim']} | Tarih: {row['Tarih']}" for _, row in giris_df.iterrows()]
        secilen_giris_sil = st.selectbox("Silmek İstediğin Depo Giriş Fişini Seç", ["Seçiniz..."] + giris_secenekleri)
        if st.button("Seçilen Depo Girişini Sil"):
            if secilen_giris_sil != "Seçiniz...":
                silinecek_parti = secilen_giris_sil.split("Parti: ")[1].split(" | ")[0].strip()
                cikis_kontrol = tx_history[(tx_history["HareketTuru"] == "Çıkış") & (tx_history["PartiNo"].astype(str).str.strip() == silinecek_parti)]
                if not cikis_kontrol.empty:
                    st.error(f"🚨 Bu parti ({silinecek_parti}) için daha sonra üretime sevk veya çıkış yapılmış! Önce ilgili çıkışları veya üretim föyünü silmelisiniz.")
                else:
                    silinen_depo_kaydi = tx_history[((tx_history["PartiNo"].astype(str).str.strip() == silinecek_parti) & (tx_history["HareketTuru"] == "Giriş"))].copy()
                    tx_history = tx_history[~((tx_history["PartiNo"].astype(str).str.strip() == silinecek_parti) & (tx_history["HareketTuru"] == "Giriş"))]
                    save_data(tx_history, STOCK_TRANSACTIONS_FILE)
                    audit_log("SILME", "DEPO_GIRISI", silinecek_parti, old_value=silinen_depo_kaydi)
                    st.success(f"'{silinecek_parti}' nolu depo giriş hareketi silindi!")
                    st.rerun()

# --- 3. CARİ VE ÜRÜN SPEK YÖNETİMİ ---
elif choice == "3. Cari dan Ürün Spek Yönetimi":
    st.header("🤝 Cari Hesap, Müşteri Özel Spek Tanımlama ve Yönetimi")
    
    tab1, tab2 = st.tabs(["Cari Tanımlama & Silme", "Cari Ürün & Spek Tanımları"])
    
    with tab1:
        st.subheader("Yeni Cari Kartı Aç")
        with st.form("cari_form", clear_on_submit=True):
            c_kodu = st.text_input("Cari Kodu (Örn: CARİ-001)")
            c_adi = st.text_input("Firma / Cari Adı")
            c_tipi = st.selectbox("Cari Tipi", ["Müşteri", "Tedarikçi", "Her İkisi"])
            c_kaydet = st.form_submit_button("Cari Kaydet")
            
            if c_kaydet and c_kodu and c_adi:
                df_cariler = load_data(CARILER_FILE, ["CariKodu", "CariAdi", "CariTipi"])
                if not df_cariler.empty and c_kodu.strip() in df_cariler["CariKodu"].astype(str).values:
                    st.error(f"'{c_kodu}' cari kodu zaten kayıtlı!")
                else:
                    new_cari = pd.DataFrame([{
                        "CariKodu": c_kodu.strip(),
                        "CariAdi": c_adi.strip(),
                        "CariTipi": c_tipi
                    }])
                    df_cariler = pd.concat([df_cariler, new_cari], ignore_index=True)
                    save_data(df_cariler, CARILER_FILE)
                    st.success(f"'{c_adi}' başarıyla kaydedildi!")
                    
        st.subheader("Kayıtlı Cariler ve Silme")
        df_cariler = load_data(CARILER_FILE, ["CariKodu", "CariAdi", "CariTipi"])
        if df_cariler.empty:
            st.info("Henüz kayıtlı cari bulunmuyor.")
        else:
            st.dataframe(df_cariler, use_container_width=True)
            
            sil_cari_sec = st.selectbox("Silmek İstediğin Cariyi Seç", ["Seçiniz..."] + df_cariler["CariAdi"].tolist(), key="del_cari_sel")
            if st.button("Seçilen Cariyi Sil"):
                if sil_cari_sec != "Seçiniz...":
                    df_cariler = df_cariler[df_cariler["CariAdi"] != sil_cari_sec]
                    save_data(df_cariler, CARILER_FILE)
                    st.success(f"'{sil_cari_sec}' cari kaydı silindi!")
                    st.rerun()

    with tab2:
        st.subheader("Cari Bazlı Ürün Spekleri, Dokümanları and Ürün Fotoğrafları Tanımla")
        df_cariler = load_data(CARILER_FILE, ["CariKodu", "CariAdi", "CariTipi"])
        master_df = load_data(MASTER_ITEMS_FILE, ["StokKodu", "StokAdi", "Depo", "Birim"])
        
        if df_cariler.empty:
            st.warning("Önce 'Cari Tanımlama' sekmesinden bir cari eklemelisin!")
        elif master_df.empty:
            st.warning("Sistemde kayıtlı stok kartı bulunmuyor.")
        else:
            mamul_master_df = master_df[master_df["Depo"] == "Mamül Deposu"]
            
            with st.form("spek_form", clear_on_submit=True):
                secilen_cari = st.selectbox("Firma (Cari) Seç", df_cariler['CariAdi'].tolist())
                
                if mamul_master_df.empty:
                    st.warning("⚠️ Sistemde 'Mamül Deposu'na ait kayıtlı ürün bulunmuyor.")
                    urun_opts = []
                else:
                    urun_opts = [f"{row['StokKodu']} - {row['StokAdi']}" for _, row in mamul_master_df.iterrows()]
                
                secilen_stok_str = st.selectbox("İlgili Mamül Stok Seçimi", urun_opts if urun_opts else ["Mamül Bulunamadı"])
                
                spek_adi = st.text_input("Spek Başlığı / Belge Adı (Örn: Müşteri Teknik Spek Dokümanı v1)")
                spek_detayi = st.text_area("Spek Detay / Özel İstekler (Örn: 28-30°Bx, 5kg Teneke Kutu, Laklı Kapak)")
                
                st.markdown("---")
                col_up1, col_up2 = st.columns(2)
                with col_up1:
                    uploaded_spek_file = st.file_uploader("📄 Spek Dosyası Yükle (PDF, Word vb.)", type=["pdf", "docx", "doc", "txt", "xlsx", "png", "jpg"])
                with col_up2:
                    uploaded_urun_foto = st.file_uploader("📸 Bu Spek'e Uygun Ürün / Numune Fotoğrafı", type=["png", "jpg", "jpeg"])

                spek_kaydet = st.form_submit_button("Spek and Dosyaları Kaydet")
                
                if spek_kaydet and secilen_cari and urun_opts and secilen_stok_str != "Mamül Bulunamadı":
                    st_kod = secilen_stok_str.split(" - ")[0]
                    
                    spec_file_path = ""
                    if uploaded_spek_file is not None:
                        sf_name = f"{secilen_cari}_{st_kod}_{int(datetime.now().timestamp())}_{uploaded_spek_file.name}"
                        spec_file_path = os.path.join(SPEC_FILE_DIR, sf_name)
                        with open(spec_file_path, "wb") as f:
                            f.write(uploaded_spek_file.getbuffer())

                    urun_foto_path = ""
                    if uploaded_urun_foto is not None:
                        uf_name = f"{secilen_cari}_{st_kod}_{int(datetime.now().timestamp())}_{uploaded_urun_foto.name}"
                        urun_foto_path = os.path.join(SPEC_PHOTO_DIR, uf_name)
                        with open(urun_foto_path, "wb") as f:
                            f.write(uploaded_urun_foto.getbuffer())

                    df_speks = load_data(SPEK_FILE, ["CariAdi", "StokKodu", "SpekAdi", "SpekDetayi", "SpekDosyaYolu", "UrunFotoYolu"])
                    new_spek = pd.DataFrame([{
                        "CariAdi": secilen_cari,
                        "StokKodu": st_kod,
                        "SpekAdi": spek_adi.strip(),
                        "SpekDetayi": spek_detayi.strip(),
                        "SpekDosyaYolu": spec_file_path,
                        "UrunFotoYolu": urun_foto_path
                    }])
                    df_speks = pd.concat([df_speks, new_spek], ignore_index=True)
                    save_data(df_speks, SPEK_FILE)
                    st.success("Ürün speki, dokümanı and uygun ürün fotoğrafı başarıyla kaydedildi!")

            st.subheader("📋 Kayıtlı Cari Spek Listesi ve Silme")
            df_speks = load_data(SPEK_FILE, ["CariAdi", "StokKodu", "SpekAdi", "SpekDetayi", "SpekDosyaYolu", "UrunFotoYolu"])
            
            if df_speks.empty:
                st.info("Henüz girilmiş özel spek bulunmuyor.")
            else:
                spek_secenekleri = [f"Firma: {row['CariAdi']} | Ürün: {row['StokKodu']} | Spek: {row['SpekAdi']}" for _, row in df_speks.iterrows()]
                secilen_spek_sil = st.selectbox("Silmek İstediğin Spek Kaydını Seç", ["Seçiniz..."] + spek_secenekleri)
                if st.button("Seçilen Spek Kaydını Sil"):
                    if secilen_spek_sil != "Seçiniz...":
                        f_adi = secilen_spek_sil.split("Firma: ")[1].split(" | ")[0].strip()
                        s_kod = secilen_spek_sil.split("Ürün: ")[1].split(" | ")[0].strip()
                        s_baslik = secilen_spek_sil.split("Spek: ")[1].strip()
                        
                        df_speks = df_speks[~((df_speks["CariAdi"] == f_adi) & (df_speks["StokKodu"] == s_kod) & (df_speks["SpekAdi"] == s_baslik))]
                        save_data(df_speks, SPEK_FILE)
                        st.success("Seçilen spek kaydı silindi!")
                        st.rerun()

                st.markdown("---")
                for idx, row in df_speks.iterrows():
                    with st.expander(f"Firma: {row['CariAdi']} | Ürün Kodu: {row['StokKodu']} | Spek: {row['SpekAdi']}"):
                        col_d1, col_d2, col_d3 = st.columns([2, 1, 1])
                        with col_d1:
                            st.markdown(f"**Cari Firma:** {row['CariAdi']}")
                            st.markdown(f"**Stok Kodu:** {row['StokKodu']}")
                            st.markdown(f"**Spek Başlığı:** {row['SpekAdi']}")
                            st.markdown(f"**Detaylar:** {row['SpekDetayi']}")
                            
                            if row['SpekDosyaYolu'] and os.path.exists(str(row['SpekDosyaYolu'])):
                                with open(row['SpekDosyaYolu'], "rb") as file_btn:
                                    st.download_button(
                                        label="📥 Spek Belgesini İndir (PDF/Dosya)",
                                        data=file_btn,
                                        file_name=os.path.basename(row['SpekDosyaYolu']),
                                        key=f"dl_spec_{idx}"
                                    )
                            else:
                                st.info("Bu spek için dosya yüklenmemiş.")
                                
                        with col_d2:
                            st.markdown("**Spek Belgesi Görseli / Önizleme**")
                            if row['SpekDosyaYolu'] and os.path.exists(str(row['SpekDosyaYolu'])) and row['SpekDosyaYolu'].lower().endswith(('png', 'jpg', 'jpeg')):
                                st.image(row['SpekDosyaYolu'], width=200)
                            else:
                                st.write("Doküman formatı veya dosya yok.")

                        with col_d3:
                            st.markdown("**Uygun Ürün Fotoğrafı**")
                            if row['UrunFotoYolu'] and os.path.exists(str(row['UrunFotoYolu'])):
                                st.image(row['UrunFotoYolu'], caption="Spek Uyumlu Ürün", width=200)
                            else:
                                st.info("Ürün fotoğrafı yüklenmemiş.")

# --- 4. ÜRETIME SEVK / REÇETELİ ÜRETİME VE MALİYET ---
elif choice == "4. Üretime Sevk / Reçeteli Üretim and Maliyet":
    st.header("📤 Dinamik Reçeteli Üretim, Parti/Lot Bazlı Sarfiyat, 2. Kalite Fire Girişi and Föy")
    
    tx_df = load_data(STOCK_TRANSACTIONS_FILE, ["Tarih", "HareketTuru", "Depo", "StokKodu", "StokAdi", "Miktar", "Birim", "BirimFiyat", "ToplamTutar", "PartiNo", "Tedarikci", "Aciklama"])
    master_df = load_data(MASTER_ITEMS_FILE, ["StokKodu", "StokAdi", "Depo", "Birim"])
    
    if tx_df.empty:
        st.warning("⚠️ Önce depoya hammadde/malzeme girişi yapmalısınız.")
    elif master_df.empty:
        st.error("🚨 Sistemde kayıtlı stok kartı bulunmuyor.")
    else:
        giris_transactions = tx_df[tx_df["HareketTuru"] == "Giriş"].copy()
        cikis_transactions = tx_df[tx_df["HareketTuru"] == "Çıkış"].copy()
        
        parti_stoklari = []
        for _, g_row in giris_transactions.iterrows():
            s_kod = g_row["StokKodu"]
            p_no = str(g_row["PartiNo"]).strip()
            d_adi = g_row["Depo"]
            
            cikan_mik = 0.0
            if not cikis_transactions.empty:
                cikan_mik = cikis_transactions[(cikis_transactions["StokKodu"] == s_kod) & (cikis_transactions["PartiNo"].astype(str).str.strip() == p_no)]["Miktar"].sum()
            
            kalan_mik = g_row["Miktar"] - cikan_mik
            if kalan_mik > 0:
                parti_stoklari.append({
                    "StokKodu": s_kod,
                    "StokAdi": g_row["StokAdi"],
                    "Depo": d_adi,
                    "Birim": g_row["Birim"],
                    "PartiNo": p_no,
                    "BirimFiyat": g_row["BirimFiyat"],
                    "KalanMiktar": kalan_mik,
                    "Etiket": f"{s_kod} - {g_row['StokAdi']} [Depo: {d_adi}] | Parti/Lot: {p_no} | Fiyat: {g_row['BirimFiyat']:,.2f} TL | Kalan: {kalan_mik:,.2f} {g_row['Birim']}"
                })
        
        df_aktif_partiler = pd.DataFrame(parti_stoklari)

        if df_aktif_partiler.empty:
            st.warning("⚠️ Depolarda sevk edilebilir aktif parti stoğu kalmadı.")
        else:
            if "recete_satir_sayisi" not in st.session_state:
                st.session_state.recete_satir_sayisi = 4
            if "fire_satir_sayisi" not in st.session_state:
                st.session_state.fire_satir_sayisi = 2

            col_b1, col_b2, col_b3 = st.columns([2, 2, 3])
            with col_b1:
                if st.button("➕ Sarfiyat Satırı Ekle"):
                    st.session_state.recete_satir_sayisi += 1
                    st.rerun()
            with col_b2:
                if st.button("➕ 2. Kalite / Fire Satırı Ekle"):
                    st.session_state.fire_satir_sayisi += 1
                    st.rerun()
            with col_b3:
                if st.button("🔄 Satırları Sıfırla"):
                    st.session_state.recete_satir_sayisi = 4
                    st.session_state.fire_satir_sayisi = 2
                    st.rerun()

            with st.form("production_form"):
                st.subheader("1️⃣ Üretilecek Mamül and Fotoğraf Bilgisi")
                c1, c2, c3 = st.columns(3)
                with c1:
                    uretim_tarihi = st.date_input("Üretim Tarihi", datetime.now())
                with c2:
                    mamul_master_df = master_df[master_df["Depo"] == "Mamül Deposu"]
                    if mamul_master_df.empty:
                        mamul_options = ["Mamül Deposunda Ürün Yok"]
                    else:
                        mamul_options = [f"{row['StokKodu']} - {row['StokAdi']}" for _, row in mamul_master_df.iterrows()]
                    
                    secilen_mamul_str = st.selectbox("Üretilen Mamül Seçimi", mamul_options)
                with c3:
                    uretilen_miktar = st.number_input("Üretilen Mamül Miktarı", min_value=0.01, step=1.0, format="%.2f")

                uploaded_photo = st.file_uploader("📸 Üretilen Ürüne Ait Fotoğraf / Kalite Kontrol Görseli Yükle", type=["png", "jpg", "jpeg"])

                st.markdown("---")
                st.subheader(f"2️⃣ Reçete / Parti Bazlı Hammadde Sarfiyatı (Stoktan Düşen)")
                
                aktif_parti_secenekleri = df_aktif_partiler["Etiket"].tolist()
                
                recete_secimleri = []
                for i in range(st.session_state.recete_satir_sayisi):
                    rc1, rc2 = st.columns([3, 1])
                    with rc1:
                        m_sec = st.selectbox(f"{i+1}. Sarf Malzemesi (Parti Bazlı)", ["Seçiniz..."] + aktif_parti_secenekleri, key=f"mat_{i}")
                    with rc2:
                        m_amt = st.number_input(f"Miktar {i+1}", min_value=0.0, step=1.0, format="%.2f", key=f"amt_{i}")
                    recete_secimleri.append((m_sec, m_amt))

                st.markdown("---")
                st.subheader(f"3️⃣ 2. Kalite / Fire Ürün Girişleri (Stokta Artış Yapan)")
                
                master_item_options = [f"{row['StokKodu']} - {row['StokAdi']} ({row['Depo']})" for _, row in master_df.iterrows()]
                
                fire_secimleri = []
                for j in range(st.session_state.fire_satir_sayisi):
                    fc1, fc2, fc3 = st.columns([3, 1, 1])
                    with fc1:
                        f_sec = st.selectbox(f"{j+1}. Fire / 2. Kalite Ürün", ["Seçiniz..."] + master_item_options, key=f"fire_mat_{j}")
                    with fc2:
                        f_amt = st.number_input(f"Fire Miktar {j+1}", min_value=0.0, step=1.0, format="%.2f", key=f"fire_amt_{j}")
                    with fc3:
                        f_fiyat = st.number_input(f"Birim Değer {j+1} (TL)", min_value=0.0, step=0.01, format="%.2f", key=f"fire_price_{j}")
                    fire_secimleri.append((f_sec, f_amt, f_fiyat))

                st.markdown("---")
                st.subheader("4️⃣ İşçilik and Ek Üretim Giderleri")
                
                ec1, ec2, ec3, ec4 = st.columns(4)
                with ec1:
                    is_emri_no = st.text_input("İş Emri / Parti No *Zorunlu and Benzersiz Olmalı*", placeholder="Örn: URT-2026-001")
                with ec2:
                    gunluk_isci_maliyeti = st.number_input("İşçi Günlük Maliyet (TL)", min_value=0.0, step=50.0, value=2500.0, format="%.2f")
                with ec3:
                    isci_sayisi = st.number_input("İşçi Sayısı", min_value=1, step=1, value=10)
                with ec4:
                    calisma_suresi_saat = st.number_input("Çalışma Süresi (Saat)", min_value=0.0, step=0.5, value=8.0)

                saatlik_tekil_maliyet = gunluk_isci_maliyeti / 8.0 if gunluk_isci_maliyeti > 0 else 0.0
                hesaplanan_iscilik_maliyeti = saatlik_tekil_maliyet * calisma_suresi_saat * isci_sayisi

                ec5, ec6 = st.columns(2)
                with ec5:
                    ek_giderler = st.number_input("Ek Enerji / Diğer Giderler (TL)", min_value=0.0, step=50.0, value=0.0, format="%.2f")
                with ec6:
                    toplam_iscilik_gideri = hesaplanan_iscilik_maliyeti + ek_giderler
                    st.markdown(f"**💰 Toplam Personel and Ek Gider:** `{toplam_iscilik_gideri:,.2f} TL`")

                aciklama = st.text_area("Üretim Notları / Açıklama")

                submitted = st.form_submit_button("Üretimi, Sarfiyatı, Fireyi and Maliyeti Onayla")
                
                if submitted:
                    secilen_recete = [(m, a) for m, a in recete_secimleri if m != "Seçiniz..." and a > 0]
                    secilen_fireler = [(f, a, pr) for f, a, pr in fire_secimleri if f != "Seçiniz..." and a > 0]

                    tx_check_df = load_data(STOCK_TRANSACTIONS_FILE, ["PartiNo"])
                    existing_parties = []
                    if not tx_check_df.empty and "PartiNo" in tx_check_df.columns:
                        existing_parties = tx_check_df["PartiNo"].astype(str).str.strip().values

                    if not is_emri_no.strip():
                        st.error("İş emri numarası zorunludur!")
                    elif is_emri_no.strip() in existing_parties:
                        st.error(f"🚨 Hata: '{is_emri_no.strip()}' iş emri/parti numarası sistemde zaten kayıtlı!")
                    elif uretilen_miktar <= 0:
                        st.error("Üretilen miktar sıfırdan büyük olmalıdır!")
                    elif secilen_mamul_str == "Mamül Deposunda Ürün Yok":
                        st.error("Lütfen önce Mamül Deposuna ait bir stok kartı tanımlayın!")
                    elif not secilen_recete:
                        st.error("En az bir adet hammadde sarfiyatı seçmeli and miktarını girmelisin!")
                    else:
                        yeni_hareketler = []
                        toplam_sarfiyat_maliyeti = 0.0
                        hata_olustu = False
                        
                        for sarf_etiket, sevk_miktari in secilen_recete:
                            s_kod = sarf_etiket.split(" - ")[0].strip()
                            depo_adi = sarf_etiket.split("[Depo: ")[1].split("]")[0].strip()
                            parti_num = sarf_etiket.split("Parti/Lot: ")[1].split(" | ")[0].strip()
                            
                            par_row = df_aktif_partiler[(df_aktif_partiler["StokKodu"] == s_kod) & (df_aktif_partiler["PartiNo"] == parti_num) & (df_aktif_partiler["Depo"] == depo_adi)]
                            
                            if par_row.empty:
                                st.error(f"⚠️ Seçilen parti ({parti_num}) bulunamadı!")
                                hata_olustu = True
                                break
                                
                            kalan_stok_miktar = par_row.iloc[0]["KalanMiktar"]
                            birim_fiyat_val = par_row.iloc[0]["BirimFiyat"]
                            stok_adi_val = par_row.iloc[0]["StokAdi"]
                            birim_val = par_row.iloc[0]["Birim"]
                            
                            if sevk_miktari > kalan_stok_miktar:
                                st.error(f"⚠️ **{s_kod} - {stok_adi_val} (Parti: {parti_num})** için girilen miktar ({sevk_miktari:,.2f}), bu partideki kalan stoğu ({kalan_stok_miktar:,.2f}) aşıyor!")
                                hata_olustu = True
                                break
                                
                            tutar = sevk_miktari * birim_fiyat_val
                            toplam_sarfiyat_maliyeti += tutar
                            
                            yeni_hareketler.append({
                                "Tarih": str(uretim_tarihi),
                                "HareketTuru": "Çıkış",
                                "Depo": depo_adi,
                                "StokKodu": s_kod,
                                "StokAdi": stok_adi_val,
                                "Birim": birim_val,
                                "Miktar": sevk_miktari,
                                "BirimFiyat": birim_fiyat_val,
                                "ToplamTutar": tutar,
                                "PartiNo": parti_num,
                                "Tedarikci": f"İş Emri: {is_emri_no.strip()}",
                                "Aciklama": f"Üretime Sarf (Seçilen Parti). {aciklama}"
                            })

                        if not hata_olustu:
                            toplam_fire_maliyeti = 0.0
                            for fire_str, fire_mik, fire_birim_fiyat in secilen_fireler:
                                f_kod = fire_str.split(" - ")[0]
                                f_depo = fire_str.split("(")[1].split(")")[0]
                                f_item_row = master_df[master_df["StokKodu"] == f_kod].iloc[0]
                                
                                f_tutar = fire_mik * fire_birim_fiyat
                                toplam_fire_maliyeti += f_tutar
                                
                                fire_giris = {
                                    "Tarih": str(uretim_tarihi),
                                    "HareketTuru": "Giriş",
                                    "Depo": f_depo,
                                    "StokKodu": f_item_row["StokKodu"],
                                    "StokAdi": f_item_row["StokAdi"],
                                    "Birim": f_item_row["Birim"],
                                    "Miktar": fire_mik,
                                    "BirimFiyat": fire_birim_fiyat,
                                    "ToplamTutar": f_tutar,
                                    "PartiNo": f"{is_emri_no.strip()}-FIRE",
                                    "Tedarikci": "2. Kalite / Fire Üretimi",
                                    "Aciklama": f"İş Emri: {is_emri_no} - Fire/2. Kalite Girişi. {aciklama}"
                                }
                                yeni_hareketler.append(fire_giris)

                            toplam_uretim_maliyeti = toplam_sarfiyat_maliyeti + toplam_iscilik_gideri - toplam_fire_maliyeti
                            if toplam_uretim_maliyeti < 0:
                                toplam_uretim_maliyeti = 0.0
                                
                            mamul_birim_maliyet = toplam_uretim_maliyeti / uretilen_miktar
                            
                            mamul_kod = secilen_mamul_str.split(" - ")[0]
                            mamul_row = master_df[master_df["StokKodu"] == mamul_kod].iloc[0]
                            
                            mamul_giris = {
                                "Tarih": str(uretim_tarihi),
                                "HareketTuru": "Giriş",
                                "Depo": "Mamül Deposu",
                                "StokKodu": mamul_row["StokKodu"],
                                "StokAdi": mamul_row["StokAdi"],
                                "Birim": mamul_row["Birim"],
                                "Miktar": uretilen_miktar,
                                "BirimFiyat": mamul_birim_maliyet,
                                "ToplamTutar": toplam_uretim_maliyeti,
                                "PartiNo": is_emri_no.strip(),
                                "Tedarikci": "Dahili Üretim",
                                "Aciklama": f"İş Emri: {is_emri_no}. Çalışma: {calisma_suresi_saat} Saat ({isci_sayisi} İşçi). İşçilik/Gider: {toplam_iscilik_gideri:,.2f} TL. Fire Düşüşü: {toplam_fire_maliyeti:,.2f} TL. {aciklama}"
                            }
                            yeni_hareketler.append(mamul_giris)
                            
                            photo_path = ""
                            if uploaded_photo is not None:
                                photo_filename = f"{is_emri_no.strip()}_{int(datetime.now().timestamp())}.png"
                                photo_path = os.path.join(PHOTO_DIR, photo_filename)
                                with open(photo_path, "wb") as f:
                                    f.write(uploaded_photo.getbuffer())

                            meta_df = load_data(PRODUCTION_META_FILE, ["IsEmriNo", "CalismaSaati", "IscilikGideri", "FotografYolu", "Notlar"])
                            meta_df = meta_df[meta_df["IsEmriNo"].astype(str) != is_emri_no.strip()]
                            new_meta = pd.DataFrame([{
                                "IsEmriNo": is_emri_no.strip(),
                                "CalismaSaati": calisma_suresi_saat,
                                "IscilikGideri": toplam_iscilik_gideri,
                                "FotografYolu": photo_path,
                                "Notlar": aciklama
                            }])
                            meta_df = pd.concat([meta_df, new_meta], ignore_index=True)
                            save_data(meta_df, PRODUCTION_META_FILE)

                            new_tx_df = pd.DataFrame(yeni_hareketler)
                            tx_df = pd.concat([tx_df, new_tx_df], ignore_index=True)
                            save_data(tx_df, STOCK_TRANSACTIONS_FILE)
                            audit_log("OLUŞTURMA", "URETIM", is_emri_no.strip(), new_value={
                                "hareketler": yeni_hareketler,
                                "meta": new_meta.to_dict(orient="records")
                            })
                            
                            st.success(f"🎉 Üretim föyü, parti bazlı sarfiyatlar and 2. kalite fire girişleri başarıyla kaydedildi!")

# --- 5. STOK DURUMU VE HAREKET PANOSU ---
elif choice == "5. Stok Durumu, Hareket Panosu and Föy Düzenleme":
    st.header("📊 Stok Durumu, Hareket Panosu, Üretim İptali and Föy Düzenleme")
    
    tx_df = load_data(STOCK_TRANSACTIONS_FILE, ["Tarih", "HareketTuru", "Depo", "StokKodu", "StokAdi", "Miktar", "Birim", "BirimFiyat", "ToplamTutar", "PartiNo", "Tedarikci", "Aciklama"])
    meta_df = load_data(PRODUCTION_META_FILE, ["IsEmriNo", "CalismaSaati", "IscilikGideri", "FotografYolu", "Notlar"])
    master_df = load_data(MASTER_ITEMS_FILE, ["StokKodu", "StokAdi", "Depo", "Birim"])
    
    if tx_df.empty:
        st.info("Henüz sistemde hiç hareket bulunmuyor.")
    else:
        st.subheader("📝 Kayıtlı Üretim Föyleri (İş Emirleri) Yönetimi & Tam Kalem Düzenleme / Silme")
        uretim_kayitlari = tx_df[(tx_df["Tedarikci"] == "Dahili Üretim") | (tx_df["Depo"] == "Mamül Deposu") & (tx_df["HareketTuru"] == "Giriş")]
        
        if not uretim_kayitlari.empty:
            is_emri_secenekleri = uretim_kayitlari["PartiNo"].astype(str).unique().tolist()
            secilen_is_emri = st.selectbox("İşlemi Yönetmek / Düzenlemek / Silmek İstediğin İş Emri / Parti No", is_emri_secenekleri)
            
            if secilen_is_emri:
                mamul_satir = uretim_kayitlari[uretim_kayitlari["PartiNo"].astype(str) == str(secilen_is_emri)].iloc[0]
                
                meta_row = meta_df[meta_df["IsEmriNo"].astype(str) == str(secilen_is_emri)]
                mevcut_sure = float(meta_row.iloc[0]["CalismaSaati"]) if not meta_row.empty and str(meta_row.iloc[0]["CalismaSaati"]) != "" else 8.0
                mevcut_gider = float(meta_row.iloc[0]["IscilikGideri"]) if not meta_row.empty and str(meta_row.iloc[0]["IscilikGideri"]) != "" else 0.0
                mevcut_foto = str(meta_row.iloc[0]["FotografYolu"]) if not meta_row.empty else ""
                mevcut_not = str(meta_row.iloc[0]["Notlar"]) if not meta_row.empty else mamul_satir["Aciklama"]

                col_f1, col_f2 = st.columns([2, 1])
                with col_f1:
                    st.markdown(f"**Üretilen Ürün:** {mamul_satir['StokKodu']} - {mamul_satir['StokAdi']}")
                    st.markdown(f"**Üretilen Miktar:** {mamul_satir['Miktar']:,.2f} {mamul_satir['Birim']}")
                    st.markdown(f"**Toplam Üretim Maliyeti:** {mamul_satir['ToplamTutar']:,.2f} TL (Birim: {mamul_satir['BirimFiyat']:,.2f} TL)")
                    st.markdown(f"**Mevcut Not:** {mevcut_not}")
                with col_f2:
                    if mevcut_foto and os.path.exists(mevcut_foto):
                        img = Image.open(mevcut_foto)
                        st.image(img, caption=f"İş Emri Fotoğrafı: {secilen_is_emri}", width=250)
                    else:
                        st.info("Bu üretime ait fotoğraf yüklenmemiş.")

                st.markdown("---")
                
                mevcut_sarfiyatlar = tx_df[(tx_df["Tedarikci"].astype(str).str.contains(str(secilen_is_emri))) & (tx_df["HareketTuru"] == "Çıkış")]
                mevcut_fireler = tx_df[tx_df["PartiNo"].astype(str) == f"{secilen_is_emri}-FIRE"]

                with st.expander(f"⚙️ '{secilen_is_emri}' Nolu Föyü and Tüm Kalemlerini Güncelle / Sil", expanded=False):
                    with st.form(f"edit_full_form_{secilen_is_emri}"):
                        st.subheader("1️⃣ Üretilen Mamül Miktarı Güncelleme")
                        yeni_uretim_miktari = st.number_input("Güncellenmiş Üretim Miktarı", min_value=0.01, value=float(mamul_satir["Miktar"]), step=1.0, format="%.2f")

                        st.markdown("---")
                        st.subheader("2️⃣ Parti Bazlı Hammadde Sarfiyat Kalemleri Güncelleme")

                        giris_tx_ed = tx_df[tx_df["HareketTuru"] == "Giriş"].copy()
                        cikis_tx_ed = tx_df[tx_df["HareketTuru"] == "Çıkış"].copy()
                        
                        parti_stoklari_ed = []
                        for _, g_row in giris_tx_ed.iterrows():
                            s_kod = g_row["StokKodu"]
                            p_no = str(g_row["PartiNo"]).strip()
                            d_adi = g_row["Depo"]
                            cikan_mik = 0.0
                            if not cikis_tx_ed.empty:
                                cikan_mik = cikis_tx_ed[(cikis_tx_ed["StokKodu"] == s_kod) & (cikis_tx_ed["PartiNo"].astype(str).str.strip() == p_no)]["Miktar"].sum()
                            kalan_mik = g_row["Miktar"] - cikan_mik
                            if kalan_mik > 0:
                                parti_stoklari_ed.append({
                                    "StokKodu": s_kod,
                                    "StokAdi": g_row["StokAdi"],
                                    "Depo": d_adi,
                                    "Birim": g_row["Birim"],
                                    "PartiNo": p_no,
                                    "BirimFiyat": g_row["BirimFiyat"],
                                    "KalanMiktar": kalan_mik,
                                    "Etiket": f"{s_kod} - {g_row['StokAdi']} [Depo: {d_adi}] | Parti/Lot: {p_no} | Fiyat: {g_row['BirimFiyat']:,.2f} TL | Kalan: {kalan_mik:,.2f} {g_row['Birim']}"
                                })
                        df_aktif_partiler_ed = pd.DataFrame(parti_stoklari_ed)
                        aktif_parti_secenekleri_ed = df_aktif_partiler_ed["Etiket"].tolist() if not df_aktif_partiler_ed.empty else []

                        edit_sarf_secimleri = []
                        satir_sayisi_edit = max(4, len(mevcut_sarfiyatlar) + 2)
                        
                        for i in range(satir_sayisi_edit):
                            default_mat = "Seçiniz..."
                            default_val = 0.0
                            if i < len(mevcut_sarfiyatlar):
                                row_s = mevcut_sarfiyatlar.iloc[i]
                                matched_et = [et for et in aktif_parti_secenekleri_ed if f"{row_s['StokKodu']}" in et and f"{row_s['PartiNo']}" in et]
                                if matched_et:
                                    default_mat = matched_et[0]
                                default_val = float(row_s["Miktar"])

                            rc1, rc2 = st.columns([3, 1])
                            with rc1:
                                m_sec_ed = st.selectbox(f"Sarf Malzemesi {i+1}", ["Seçiniz..."] + aktif_parti_secenekleri_ed, index=aktif_parti_secenekleri_ed.index(default_mat)+1 if default_mat in aktif_parti_secenekleri_ed else 0, key=f"edit_mat_{secilen_is_emri}_{i}")
                            with rc2:
                                m_amt_ed = st.number_input(f"Miktar {i+1}", min_value=0.0, value=default_val, step=1.0, format="%.2f", key=f"edit_amt_{secilen_is_emri}_{i}")
                            edit_sarf_secimleri.append((m_sec_ed, m_amt_ed))

                        st.markdown("---")
                        st.subheader("3️⃣ 2. Kalite / Fire Kalemleri")
                        edit_fire_secimleri = []
                        fire_satir_sayisi_edit = max(2, len(mevcut_fireler) + 1)
                        stok_options_edit = [f"{row['StokKodu']} - {row['StokAdi']} ({row['Depo']})" for _, row in master_df.iterrows()]

                        for j in range(fire_satir_sayisi_edit):
                            def_f_mat = "Seçiniz..."
                            def_f_mik = 0.0
                            def_f_fiy = 0.0
                            if j < len(mevcut_fireler):
                                row_f = mevcut_fireler.iloc[j]
                                match_f_str = f"{row_f['StokKodu']} - {row_f['StokAdi']} ({row_f['Depo']})"
                                if match_f_str in stok_options_edit:
                                    def_f_mat = match_f_str
                                def_f_mik = float(row_f["Miktar"])
                                def_f_fiy = float(row_f["BirimFiyat"])

                            fc1, fc2, fc3 = st.columns([3, 1, 1])
                            with fc1:
                                f_sec_ed = st.selectbox(f"Fire / 2. Kalite {j+1}", ["Seçiniz..."] + stok_options_edit, index=stok_options_edit.index(def_f_mat)+1 if def_f_mat in stok_options_edit else 0, key=f"edit_fire_mat_{secilen_is_emri}_{j}")
                            with fc2:
                                f_amt_ed = st.number_input(f"Fire Miktar {j+1}", min_value=0.0, value=def_f_mik, step=1.0, format="%.2f", key=f"edit_fire_amt_{secilen_is_emri}_{j}")
                            with fc3:
                                f_fiyat_ed = st.number_input(f"Birim Değer {j+1} (TL)", min_value=0.0, value=def_f_fiy, step=0.01, format="%.2f", key=f"edit_fire_price_{secilen_is_emri}_{j}")
                            edit_fire_secimleri.append((f_sec_ed, f_amt_ed, f_fiyat_ed))

                        st.markdown("---")
                        st.subheader("4️⃣ Çalışma Süresi, İşçilik and Diğer Giderler")
                        ed_col1, ed_col2 = st.columns(2)
                        with ed_col1:
                            yeni_sure = st.number_input("Çalışma Süresi (Saat)", min_value=0.0, value=mevcut_sure, step=0.5)
                        with ed_col2:
                            yeni_gider = st.number_input("Toplam Personel & Ek Gider (TL)", min_value=0.0, value=mevcut_gider, step=100.0, format="%.2f")
                        
                        yeni_fotograf = st.file_uploader("Yeni / Değiştirilecek Fotoğraf Yükle", type=["png", "jpg", "jpeg"], key=f"up_{secilen_is_emri}")
                        yeni_not = st.text_area("Föy / Üretim Notunu Güncelle", value=mevcut_not)

                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            guncelle_pressed = st.form_submit_button("💾 Üretim Föyünü and Tüm Kalemleri Güncelle")
                        with col_btn2:
                            sil_pressed = st.form_submit_button("🗑️ Üretimi Tamamen İptal Et & Sil")

                        if sil_pressed:
                            mask_mamul = (tx_df["PartiNo"].astype(str) == str(secilen_is_emri)) & (tx_df["Tedarikci"] == "Dahili Üretim")
                            mask_sarf_fire = tx_df["Tedarikci"].astype(str).str.contains(str(secilen_is_emri), regex=False) | (tx_df["PartiNo"].astype(str) == f"{secilen_is_emri}-FIRE")
                            silinen_uretim = tx_df[mask_mamul | mask_sarf_fire].copy()
                            tx_df = tx_df[~(mask_mamul | mask_sarf_fire)]
                            save_data(tx_df, STOCK_TRANSACTIONS_FILE)
                            audit_log("SILME", "URETIM", secilen_is_emri, old_value=silinen_uretim)
                            st.success(f"✅ '{secilen_is_emri}' nolu iş emri silindi and tüm hareketler iptal edildi!")
                            st.rerun()

                        if guncelle_pressed:
                            secilen_yeni_recete = [(m, a) for m, a in edit_sarf_secimleri if m != "Seçiniz..." and a > 0]
                            secilen_yeni_fireler = [(f, a, pr) for f, a, pr in edit_fire_secimleri if f != "Seçiniz..." and a > 0]

                            if yeni_uretim_miktari <= 0:
                                st.error("Üretilen miktar sıfırdan büyük olmalıdır!")
                            elif not secilen_yeni_recete:
                                st.error("En az bir adet hammadde sarfiyatı seçilmelidir!")
                            else:
                                eski_uretim_snapshot = {
                                    "hareketler": pd.concat([mevcut_sarfiyatlar, mevcut_fireler, pd.DataFrame([mamul_satir])], ignore_index=True).to_dict(orient="records"),
                                    "meta": meta_row.to_dict(orient="records")
                                }
                                mask_mamul_eski = (tx_df["PartiNo"].astype(str) == str(secilen_is_emri)) & (tx_df["Tedarikci"] == "Dahili Üretim")
                                mask_sarf_eski = tx_df["Tedarikci"].astype(str).str.contains(str(secilen_is_emri))
                                mask_fire_eski = tx_df["PartiNo"].astype(str) == f"{secilen_is_emri}-FIRE"
                                tx_df = tx_df[~(mask_mamul_eski | mask_sarf_eski | mask_fire_eski)]

                                yeni_eklenen_hareketler = []
                                toplam_sarfiyat_maliyeti = 0.0
                                hata_olustu_ed = False

                                for sarf_etiket_ed, sevk_miktari_ed in secilen_yeni_recete:
                                    s_kod_ed = sarf_etiket_ed.split(" - ")[0].strip()
                                    depo_adi_ed = sarf_etiket_ed.split("[Depo: ")[1].split("]")[0].strip()
                                    parti_num_ed = sarf_etiket_ed.split("Parti/Lot: ")[1].split(" | ")[0].strip()

                                    par_row_ed = df_aktif_partiler_ed[(df_aktif_partiler_ed["StokKodu"] == s_kod_ed) & (df_aktif_partiler_ed["PartiNo"] == parti_num_ed) & (df_aktif_partiler_ed["Depo"] == depo_adi_ed)]
                                    
                                    if par_row_ed.empty:
                                        st.error(f"⚠️ Seçilen parti ({parti_num_ed}) bulunamadı!")
                                        hata_olustu_ed = True
                                        break
                                        
                                    kalan_stok_ed = par_row_ed.iloc[0]["KalanMiktar"]
                                    birim_fiyat_ed = par_row_ed.iloc[0]["BirimFiyat"]
                                    stok_adi_ed = par_row_ed.iloc[0]["StokAdi"]
                                    birim_val_ed = par_row_ed.iloc[0]["Birim"]

                                    if sevk_miktari_ed > kalan_stok_ed:
                                        st.error(f"⚠️ **{s_kod_ed} - {stok_adi_ed} (Parti: {parti_num_ed})** için girilen miktar ({sevk_miktari_ed:,.2f}), bu partideki kalan stoğu ({kalan_stok_ed:,.2f}) aşıyor!")
                                        hata_olustu_ed = True
                                        break

                                    tutar_ed = sevk_miktari_ed * birim_fiyat_ed
                                    toplam_sarfiyat_maliyeti += tutar_ed

                                    yeni_eklenen_hareketler.append({
                                        "Tarih": mamul_satir["Tarih"],
                                        "HareketTuru": "Çıkış",
                                        "Depo": depo_adi_ed,
                                        "StokKodu": s_kod_ed,
                                        "StokAdi": stok_adi_ed,
                                        "Birim": birim_val_ed,
                                        "Miktar": sevk_miktari_ed,
                                        "BirimFiyat": birim_fiyat_ed,
                                        "ToplamTutar": tutar_ed,
                                        "PartiNo": parti_num_ed,
                                        "Tedarikci": f"İş Emri: {str(secilen_is_emri).strip()}",
                                        "Aciklama": f"Üretime Sarf (Güncellendi). {yeni_not}"
                                    })

                                if not hata_olustu_ed:
                                    toplam_fire_maliyeti = 0.0
                                    for fire_str, fire_mik, fire_birim_fiyat in secilen_yeni_fireler:
                                        f_kod = fire_str.split(" - ")[0]
                                        f_depo = fire_str.split("(")[1].split(")")[0]
                                        f_item_row = master_df[master_df["StokKodu"] == f_kod].iloc[0]

                                        f_tutar = fire_mik * fire_birim_fiyat
                                        toplam_fire_maliyeti += f_tutar

                                        fire_giris = {
                                            "Tarih": mamul_satir["Tarih"],
                                            "HareketTuru": "Giriş",
                                            "Depo": f_depo,
                                            "StokKodu": f_item_row["StokKodu"],
                                            "StokAdi": f_item_row["StokAdi"],
                                            "Birim": f_item_row["Birim"],
                                            "Miktar": fire_mik,
                                            "BirimFiyat": fire_birim_fiyat,
                                            "ToplamTutar": f_tutar,
                                            "PartiNo": f"{str(secilen_is_emri).strip()}-FIRE",
                                            "Tedarikci": "2. Kalite / Fire Üretimi",
                                            "Aciklama": f"İş Emri: {secilen_is_emri} - Fire/2. Kalite Girişi (Güncellendi). {yeni_not}"
                                        }
                                        yeni_eklenen_hareketler.append(fire_giris)

                                    toplam_uretim_maliyeti = toplam_sarfiyat_maliyeti + yeni_gider - toplam_fire_maliyeti
                                    if toplam_uretim_maliyeti < 0:
                                        toplam_uretim_maliyeti = 0.0

                                    yeni_birim_maliyet = toplam_uretim_maliyeti / yeni_uretim_miktari

                                    mamul_giris = {
                                        "Tarih": mamul_satir["Tarih"],
                                        "HareketTuru": "Giriş",
                                        "Depo": "Mamül Deposu",
                                        "StokKodu": mamul_satir["StokKodu"],
                                        "StokAdi": mamul_satir["StokAdi"],
                                        "Birim": mamul_satir["Birim"],
                                        "Miktar": yeni_uretim_miktari,
                                        "BirimFiyat": yeni_birim_maliyet,
                                        "ToplamTutar": toplam_uretim_maliyeti,
                                        "PartiNo": str(secilen_is_emri),
                                        "Tedarikci": "Dahili Üretim",
                                        "Aciklama": f"İş Emri: {secilen_is_emri}. Çalışma: {yeni_sure} Saat. İşçilik/Gider: {yeni_gider:,.2f} TL. Fire Düşüşü: {toplam_fire_maliyeti:,.2f} TL. {yeni_not}"
                                    }
                                    yeni_eklenen_hareketler.append(mamul_giris)

                                    tx_df = pd.concat([tx_df, pd.DataFrame(yeni_eklenen_hareketler)], ignore_index=True)
                                    save_data(tx_df, STOCK_TRANSACTIONS_FILE)

                                    final_photo_path = mevcut_foto
                                    if yeni_fotograf is not None:
                                        photo_filename = f"{secilen_is_emri}_{int(datetime.now().timestamp())}.png"
                                        final_photo_path = os.path.join(PHOTO_DIR, photo_filename)
                                        with open(final_photo_path, "wb") as f:
                                            f.write(yeni_fotograf.getbuffer())

                                    meta_df = meta_df[meta_df["IsEmriNo"].astype(str) != str(secilen_is_emri)]
                                    new_meta = pd.DataFrame([{
                                        "IsEmriNo": str(secilen_is_emri),
                                        "CalismaSaati": yeni_sure,
                                        "IscilikGideri": yeni_gider,
                                        "FotografYolu": final_photo_path,
                                        "Notlar": yeni_not
                                    }])
                                    meta_df = pd.concat([meta_df, new_meta], ignore_index=True)
                                    save_data(meta_df, PRODUCTION_META_FILE)
                                    audit_log("GUNCELLEME", "URETIM", secilen_is_emri, old_value=eski_uretim_snapshot, new_value={
                                        "hareketler": yeni_eklenen_hareketler,
                                        "meta": new_meta.to_dict(orient="records")
                                    })

                                    st.success(f"✨ '{secilen_is_emri}' nolu üretim föyü başarıyla güncellendi!")
                                    st.rerun()

        else:
            st.info("Sistemde düzenlenebilecek kayıtlı bir dahili üretim bulunmuyor.")

        st.markdown("---")

        depo_listesi = ["Tümü"] + list(tx_df["Depo"].unique())
        secilen_depo_filtre = st.selectbox("📂 Depo Filtrele", depo_listesi)
        
        # Güncel stok değerini lot bazında hesapla: kalan miktar x lotun giriş/üretim birim maliyeti.
        # Böylece daha önce çıkmış/sevk edilmiş malların bedeli stok değerine dahil edilmez.
        giris_deger_df = tx_df[tx_df["HareketTuru"] == "Giriş"].copy()
        cikis_deger_df = tx_df[tx_df["HareketTuru"] == "Çıkış"].copy()
        kalan_stok_degeri = 0.0
        kalan_lot_adedi = 0
        for _, g_row in giris_deger_df.iterrows():
            s_kod = str(g_row["StokKodu"])
            p_no = str(g_row["PartiNo"]).strip()
            depo = str(g_row["Depo"])
            if secilen_depo_filtre != "Tümü" and depo != secilen_depo_filtre:
                continue
            cikan = cikis_deger_df[(cikis_deger_df["StokKodu"].astype(str) == s_kod) &
                                   (cikis_deger_df["PartiNo"].astype(str).str.strip() == p_no)]["Miktar"].sum()
            kalan = max(float(g_row["Miktar"]) - float(cikan), 0.0)
            if kalan > 0:
                kalan_stok_degeri += kalan * float(g_row["BirimFiyat"])
                kalan_lot_adedi += 1

        st.markdown("---")
        col_kpi1, col_kpi2 = st.columns(2)
        with col_kpi1:
            depo_etiketi = secilen_depo_filtre if secilen_depo_filtre != "Tümü" else "Tüm Depolar"
            st.metric(label=f"💰 Depoda Kalan Malların Bedeli ({depo_etiketi})", value=f"{kalan_stok_degeri:,.2f} TL")
        with col_kpi2:
            st.metric(label="📦 Stokta Kalan Lot Sayısı", value=f"{kalan_lot_adedi:,} Adet")
        st.markdown("---")

        temp_all = tx_df.copy()
        temp_all["NetMiktar"] = temp_all.apply(lambda row: row["Miktar"] if row["HareketTuru"] == "Giriş" else -row["Miktar"], axis=1)
        global_summary_df = temp_all.groupby(["StokKodu", "StokAdi", "Depo", "Birim"])["NetMiktar"].sum().reset_index()
        global_summary_df.columns = ["Stok Kodu", "Stok Adı", "Depo", "Birim", "Net Miktar"]
        
        if secilen_depo_filtre != "Tümü":
            summary_df = global_summary_df[global_summary_df["Depo"] == secilen_depo_filtre]
        else:
            summary_df = global_summary_df.copy()
            
        st.subheader("📦 Seçilen Depodaki Güncel Net Stoklar")
        if summary_df.empty:
            st.info("Bu depoda henüz stok hareketi bulunmuyor.")
        else:
            styled_summary = summary_df.style.format({
                "Net Miktar": "{:,.2f}"
            })
            st.dataframe(styled_summary, use_container_width=True)
            
            def convert_df_to_excel(df):
                html_table = df.to_html(index=False, escape=False)
                excel_html = f"""
                <html xmlns:o="urn:schemas-microsoft-com:office:office" 
                      xmlns:x="urn:schemas-microsoft-com:office:excel" 
                      xmlns="http://www.w3.org/TR/REC-html40">
                <head>
                <meta http-equiv="content-type" content="text/html; charset=UTF-8">
                <!--[if gte mso 9]>
                <xml>
                <x:ExcelWorkbook>
                <x:ExcelWorksheets>
                <x:ExcelWorksheet>
                <x:Name>Stok Durumu</x:Name>
                <x:WorksheetOptions>
                <x:DisplayGridlines/>
                </x:WorksheetOptions>
                </x:ExcelWorksheet>
                </x:ExcelWorksheets>
                </x:ExcelWorkbook>
                </xml>
                <![endif]-->
                </head>
                <body>
                {html_table}
                </body>
                </html>
                """
                return excel_html.encode('utf-8')

            excel_data = convert_df_to_excel(summary_df)
            
            st.download_button(
                label="📥 Güncel Stok Raporunu Excel Olarak İndir (.xls)",
                data=excel_data,
                file_name=f"stok_durumu_{secilen_depo_filtre}.xls",
                mime="application/vnd.ms-excel"
            )

        # Stok kartı bazında tüm giriş / çıkış hareketleri
        st.markdown("---")
        st.subheader("🔎 Stok Kartı Bazlı Giriş / Çıkış Hareketleri")
        stok_kartlari = (tx_df[["StokKodu", "StokAdi"]].drop_duplicates()
                         .sort_values(["StokKodu", "StokAdi"]))
        stok_kart_secenekleri = [f"{r['StokKodu']} - {r['StokAdi']}" for _, r in stok_kartlari.iterrows()]
        if stok_kart_secenekleri:
            secilen_stok_kart = st.selectbox("Stok Kartı Seç", stok_kart_secenekleri, key="stok_karti_hareket_sec")
            secilen_stok_kodu = secilen_stok_kart.split(" - ", 1)[0].strip()
            kart_hareketleri = tx_df[tx_df["StokKodu"].astype(str) == secilen_stok_kodu].copy()
            kart_hareketleri["Giriş Miktarı"] = kart_hareketleri.apply(lambda r: r["Miktar"] if r["HareketTuru"] == "Giriş" else 0.0, axis=1)
            kart_hareketleri["Çıkış Miktarı"] = kart_hareketleri.apply(lambda r: r["Miktar"] if r["HareketTuru"] == "Çıkış" else 0.0, axis=1)
            toplam_giris = kart_hareketleri["Giriş Miktarı"].sum()
            toplam_cikis = kart_hareketleri["Çıkış Miktarı"].sum()
            net_stok = toplam_giris - toplam_cikis
            birim = str(kart_hareketleri.iloc[0]["Birim"]) if not kart_hareketleri.empty else ""
            hk1, hk2, hk3 = st.columns(3)
            hk1.metric("⬇️ Toplam Giriş", f"{toplam_giris:,.2f} {birim}")
            hk2.metric("⬆️ Toplam Çıkış", f"{toplam_cikis:,.2f} {birim}")
            hk3.metric("📦 Net Stok", f"{net_stok:,.2f} {birim}")
            gosterim_kolonlari = ["Tarih", "HareketTuru", "Depo", "PartiNo", "Miktar", "Birim", "BirimFiyat", "ToplamTutar", "Tedarikci", "Aciklama"]
            kart_gosterim = kart_hareketleri[gosterim_kolonlari].sort_index(ascending=False)
            st.dataframe(kart_gosterim.style.format({"Miktar":"{:,.2f}", "BirimFiyat":"{:,.2f} TL", "ToplamTutar":"{:,.2f} TL"}), use_container_width=True)
        else:
            st.info("Stok kartı hareketi bulunmuyor.")

# --- 6. SEVKİYAT & ÇIKIŞ YÖNETİMİ (İLÇE TARIM & FOTO) ---
elif choice == "6. Sevkiyat & Çıkış Yönetimi (İlçe Tarım & Foto)":
    st.header("🚚 Mamül Sevkiyat and Çıkış Yönetimi (İlçe Tarım Evrakları & Sevkiyat Fotoğrafı)")
    
    tx_df = load_data(STOCK_TRANSACTIONS_FILE, ["Tarih", "HareketTuru", "Depo", "StokKodu", "StokAdi", "Miktar", "Birim", "BirimFiyat", "ToplamTutar", "PartiNo", "Tedarikci", "Aciklama"])
    df_cariler = load_data(CARILER_FILE, ["CariKodu", "CariAdi", "CariTipi"])
    
    if tx_df.empty:
        st.warning("⚠️ Sistemde henüz stok hareketi bulunmuyor.")
    else:
        giris_txs = tx_df[tx_df["HareketTuru"] == "Giriş"].copy()
        cikis_txs = tx_df[tx_df["HareketTuru"] == "Çıkış"].copy()
        
        mamul_partileri = []
        for _, g_row in giris_txs.iterrows():
            if g_row["Depo"] == "Mamül Deposu":
                s_kod = g_row["StokKodu"]
                p_no = str(g_row["PartiNo"]).strip()
                
                cikan_mik = 0.0
                if not cikis_txs.empty:
                    cikan_mik = cikis_txs[(cikis_txs["StokKodu"] == s_kod) & (cikis_txs["PartiNo"].astype(str).str.strip() == p_no)]["Miktar"].sum()
                
                kalan_mik = g_row["Miktar"] - cikan_mik
                if kalan_mik > 0:
                    mamul_partileri.append({
                        "StokKodu": s_kod,
                        "StokAdi": g_row["StokAdi"],
                        "Birim": g_row["Birim"],
                        "PartiNo": p_no,
                        "BirimFiyat": g_row["BirimFiyat"],
                        "KalanMiktar": kalan_mik,
                        "Etiket": f"{s_kod} - {g_row['StokAdi']} | Parti/Lot: {p_no} | Kalan: {kalan_mik:,.2f} {g_row['Birim']}"
                    })
        
        df_mamul_partiler = pd.DataFrame(mamul_partileri)

        if df_mamul_partiler.empty:
            st.warning("⚠️ Mamül Deposunda sevk edilebilir aktif ürün/parti kalmadı.")
        else:
            if "sevk_satir_sayisi" not in st.session_state:
                st.session_state.sevk_satir_sayisi = 2

            if st.button("➕ Sevkiyat Kalemi Ekle"):
                st.session_state.sevk_satir_sayisi += 1
                st.rerun()

            with st.form("shipment_form", clear_on_submit=True):
                st.subheader("1️⃣ Sevkiyat ve Müşteri Bilgileri")
                sc1, sc2, sc3 = st.columns(3)
                with sc1:
                    sevk_tarihi = st.date_input("Sevkiyat Tarihi", datetime.now())
                with sc2:
                    cari_secenekleri = df_cariler["CariAdi"].tolist() if not df_cariler.empty else ["Cari Bulunamadı"]
                    secilen_musteri = st.selectbox("Sevk Edilen Müşteri (Cari)", cari_secenekleri)
                with sc3:
                    irsaliye_sevkiyat_no = st.text_input("Sevk İrsaliye / Fatura No *Zorunlu*", placeholder="Örn: IRS-2026-001")

                st.markdown("---")
                st.subheader("2️⃣ Sevk Edilecek Mamüller, Parti Seçimi ve Satış Fiyatı")
                
                mamul_secenekleri = df_mamul_partiler["Etiket"].tolist()
                
                sevk_kalemleri = []
                for i in range(st.session_state.sevk_satir_sayisi):
                    sk1, sk2, sk3 = st.columns([2, 1, 1])
                    with sk1:
                        m_sevk_sec = st.selectbox(f"{i+1}. Mamül Parti Seçimi", ["Seçiniz..."] + mamul_secenekleri, key=f"sevk_item_{i}")
                    with sk2:
                        m_sevk_mik = st.number_input(f"Sevk Miktar {i+1}", min_value=0.0, step=1.0, format="%.2f", key=f"sevk_amt_{i}")
                    with sk3:
                        m_sevk_fiyat = st.number_input(f"Birim Satış Fiyatı {i+1} (TL)", min_value=0.0, step=0.01, format="%.2f", key=f"sevk_price_{i}")
                    sevk_kalemleri.append((m_sevk_sec, m_sevk_mik, m_sevk_fiyat))

                st.markdown("---")
                st.subheader("3️⃣ Sevkiyat Görseli and İlçe Tarım Evrakları Arşivi")
                sc_up1, sc_up2 = st.columns(2)
                with sc_up1:
                    uploaded_shipment_photo = st.file_uploader("📸 Sevkiyat / Yükleme Fotoğrafı (Araç, Palet vb.)", type=["png", "jpg", "jpeg"])
                with sc_up2:
                    uploaded_ilce_tarim_doc = st.file_uploader("🏛️ İlçe Tarım Evrakları / Kontrol Belgesi (PDF, Resim vb.)", type=["pdf", "png", "jpg", "jpeg"])

                sevk_notu = st.text_area("Sevkiyat Açıklaması / Plaka / Şoför Bilgileri")

                submitted_shipment = st.form_submit_button("Sevkiyatı ve Çıkışı Onayla")

                if submitted_shipment:
                    secilen_sevk_kalemleri = [(m, a, f) for m, a, f in sevk_kalemleri if m != "Seçiniz..." and a > 0]

                    if not irsaliye_sevkiyat_no.strip():
                        st.error("Sevk irsaliye / fatura numarası zorunludur!")
                    elif not secilen_sevk_kalemleri:
                        st.error("En az bir adet mamül sevkiyat kalemi seçmeli and miktarını girmelisin!")
                    else:
                        hata_sevk = False
                        yeni_sevk_hareketleri = []

                        for s_etiket, s_miktar, s_fiyat in secilen_sevk_kalemleri:
                            s_kod = s_etiket.split(" - ")[0].strip()
                            p_no = s_etiket.split("Parti/Lot: ")[1].split(" | ")[0].strip()

                            m_row = df_mamul_partiler[(df_mamul_partiler["StokKodu"] == s_kod) & (df_mamul_partiler["PartiNo"] == p_no)]

                            if m_row.empty:
                                st.error(f"⚠️ Seçilen parti ({p_no}) bulunamadı!")
                                hata_sevk = True
                                break

                            kalan_stk = m_row.iloc[0]["KalanMiktar"]
                            if s_miktar > kalan_stk:
                                st.error(f"⚠️ **{s_kod} (Parti: {p_no})** için girilen sevk miktarı ({s_miktar:,.2f}), depodaki kalan stoğu ({kalan_stk:,.2f}) aşıyor!")
                                hata_sevk = True
                                break

                            stok_adi = m_row.iloc[0]["StokAdi"]
                            birim_val = m_row.iloc[0]["Birim"]
                            
                            satis_birim_fiy = s_fiyat if s_fiyat > 0 else m_row.iloc[0]["BirimFiyat"]
                            tutar_val = s_miktar * satis_birim_fiy

                            yeni_sevk_hareketleri.append({
                                "Tarih": str(sevk_tarihi),
                                "HareketTuru": "Çıkış",
                                "Depo": "Mamül Deposu",
                                "StokKodu": s_kod,
                                "StokAdi": stok_adi,
                                "Birim": birim_val,
                                "Miktar": s_miktar,
                                "BirimFiyat": satis_birim_fiy,
                                "ToplamTutar": tutar_val,
                                "PartiNo": p_no,
                                "Tedarikci": f"Müşteri Sevkiyat: {secilen_musteri}",
                                "Aciklama": f"İrsaliye: {irsaliye_sevkiyat_no.strip()}. {sevk_notu}"
                            })

                        if not hata_sevk:
                            s_foto_path = ""
                            if uploaded_shipment_photo is not None:
                                sf_name = f"sevk_foto_{irsaliye_sevkiyat_no.strip()}_{int(datetime.now().timestamp())}.png"
                                s_foto_path = os.path.join(SHIPMENT_PHOTO_DIR, sf_name)
                                with open(s_foto_path, "wb") as f:
                                    f.write(uploaded_shipment_photo.getbuffer())

                            s_doc_path = ""
                            if uploaded_ilce_tarim_doc is not None:
                                sd_name = f"ilce_tarim_{irsaliye_sevkiyat_no.strip()}_{int(datetime.now().timestamp())}_{uploaded_ilce_tarim_doc.name}"
                                s_doc_path = os.path.join(SHIPMENT_DOC_DIR, sd_name)
                                with open(s_doc_path, "wb") as f:
                                    f.write(uploaded_ilce_tarim_doc.getbuffer())

                            meta_ship_df = load_data(SHIPMENT_META_FILE, ["IrsaliyeNo", "MusteriAdi", "SevkFotoYolu", "IlceTarimDocYolu", "Notlar"])
                            meta_ship_df = meta_ship_df[meta_ship_df["IrsaliyeNo"].astype(str) != irsaliye_sevkiyat_no.strip()]
                            new_ship_meta = pd.DataFrame([{
                                "IrsaliyeNo": irsaliye_sevkiyat_no.strip(),
                                "MusteriAdi": secilen_musteri,
                                "SevkFotoYolu": s_foto_path,
                                "IlceTarimDocYolu": s_doc_path,
                                "Notlar": sevk_notu
                            }])
                            meta_ship_df = pd.concat([meta_ship_df, new_ship_meta], ignore_index=True)
                            save_data(meta_ship_df, SHIPMENT_META_FILE)

                            tx_df = pd.concat([tx_df, pd.DataFrame(yeni_sevk_hareketleri)], ignore_index=True)
                            save_data(tx_df, STOCK_TRANSACTIONS_FILE)
                            audit_log("OLUŞTURMA", "SEVKIYAT", irsaliye_sevkiyat_no.strip(), new_value={
                                "hareketler": yeni_sevk_hareketleri,
                                "meta": new_ship_meta.to_dict(orient="records")
                            })

                            st.success(f"🎉 Sevkiyat başarıyla gerçekleştirildi, fiyatlandırma işlendi, stoktan düşüldü, İlçe Tarım belgesi ve sevkiyat fotoğrafı arşivlendi!")

    # Müşteri sevkiyatlarından oluşan satış cirosu
    st.markdown("---")
    st.subheader("💰 Sevkiyat Ciro Özeti")
    sevk_ciro_df = tx_df[(tx_df["HareketTuru"] == "Çıkış") &
                         (tx_df["Tedarikci"].astype(str).str.startswith("Müşteri Sevkiyat:", na=False))].copy()
    toplam_ciro = sevk_ciro_df["ToplamTutar"].sum() if not sevk_ciro_df.empty else 0.0
    sevk_irsaliyeler = load_data(SHIPMENT_META_FILE, ["IrsaliyeNo", "MusteriAdi", "SevkFotoYolu", "IlceTarimDocYolu", "Notlar"])
    irsaliye_adedi = sevk_irsaliyeler["IrsaliyeNo"].astype(str).nunique() if not sevk_irsaliyeler.empty else 0
    ortalama_irsaliye = toplam_ciro / irsaliye_adedi if irsaliye_adedi else 0.0
    ck1, ck2, ck3 = st.columns(3)
    ck1.metric("💵 Toplam Sevkiyat Cirosu", f"{toplam_ciro:,.2f} TL")
    ck2.metric("🚚 Sevkiyat / İrsaliye Sayısı", f"{irsaliye_adedi:,}")
    ck3.metric("📊 Ortalama İrsaliye Tutarı", f"{ortalama_irsaliye:,.2f} TL")
    if not sevk_ciro_df.empty:
        sevk_ciro_df["Müşteri"] = sevk_ciro_df["Tedarikci"].astype(str).str.replace("Müşteri Sevkiyat:", "", regex=False).str.strip()
        musteri_ciro = sevk_ciro_df.groupby("Müşteri", as_index=False)["ToplamTutar"].sum()
        musteri_ciro.columns = ["Müşteri", "Ciro (TL)"]
        musteri_ciro = musteri_ciro.sort_values("Ciro (TL)", ascending=False)
        st.markdown("**Müşteri Bazlı Ciro**")
        st.dataframe(musteri_ciro.style.format({"Ciro (TL)":"{:,.2f} TL"}), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("📋 Kayıtlı Sevkiyatlar and Arşiv (İlçe Tarım, Fiyatlar, Fotoğraflar & İptal/Silme)")
    meta_ship_df = load_data(SHIPMENT_META_FILE, ["IrsaliyeNo", "MusteriAdi", "SevkFotoYolu", "IlceTarimDocYolu", "Notlar"])
    
    if meta_ship_df.empty:
        st.info("Henüz kayıtlı sevkiyat bulunmuyor.")
    else:
        # DETAYLI SEVKİYAT EXCEL DÖKÜMÜ İÇİN LİSTE OLUŞTURMA
        detayli_sevk_listesi = []
        for _, s_row in meta_ship_df.iterrows():
            irs_no = str(s_row["IrsaliyeNo"]).strip()
            musteri = s_row["MusteriAdi"]
            notlar = s_row["Notlar"]
            
            # Bu irsaliyeye ait çıkış kalemlerini bulalım
            irs_kalemleri_df = tx_df[(tx_df["HareketTuru"] == "Çıkış") & (tx_df["Aciklama"].astype(str).str.contains(irs_no))]
            
            if not irs_kalemleri_df.empty:
                for _, ik in irs_kalemleri_df.iterrows():
                    detayli_sevk_listesi.append({
                        "Sevkiyat Tarihi": ik["Tarih"],
                        "İrsaliye No": irs_no,
                        "Müşteri Adı": musteri,
                        "Stok Kodu": ik["StokKodu"],
                        "Ürün / Malzeme Adı": ik["StokAdi"],
                        "Parti / Lot No": ik["PartiNo"],
                        "Miktar": ik["Miktar"],
                        "Birim": ik["Birim"],
                        "Birim Fiyat (TL)": ik["BirimFiyat"],
                        "Toplam Tutar (TL)": ik["ToplamTutar"],
                        "Açıklama / Notlar": notlar
                    })
            else:
                detayli_sevk_listesi.append({
                    "Sevkiyat Tarihi": "-",
                    "İrsaliye No": irs_no,
                    "Müşteri Adı": musteri,
                    "Stok Kodu": "-",
                    "Ürün / Malzeme Adı": "-",
                    "Parti / Lot No": "-",
                    "Miktar": 0.0,
                    "Birim": "-",
                    "Birim Fiyat (TL)": 0.0,
                    "Toplam Tutar (TL)": 0.0,
                    "Açıklama / Notlar": notlar
                })

        df_detayli_sevkiyat_excel = pd.DataFrame(detayli_sevk_listesi)

        def convert_shipment_to_excel(df):
            html_table = df.to_html(index=False, escape=False)
            excel_html = f"""
            <html xmlns:o="urn:schemas-microsoft-com:office:office" 
                  xmlns:x="urn:schemas-microsoft-com:office:excel" 
                  xmlns="http://www.w3.org/TR/REC-html40">
            <head>
            <meta http-equiv="content-type" content="text/html; charset=UTF-8">
            <!--[if gte mso 9]>
            <xml>
            <x:ExcelWorkbook>
            <x:ExcelWorksheets>
            <x:ExcelWorksheet>
            <x:Name>Sevkiyat Detayli Arsite</x:Name>
            <x:WorksheetOptions>
            <x:DisplayGridlines/>
            </x:WorksheetOptions>
            </x:ExcelWorksheet>
            </x:ExcelWorksheets>
            </x:ExcelWorkbook>
            </xml>
            <![endif]-->
            </head>
            <body>
            {html_table}
            </body>
            </html>
            """
            return excel_html.encode('utf-8')

        shipment_excel_data = convert_shipment_to_excel(df_detayli_sevkiyat_excel)
        st.download_button(
            label="📥 Detaylı Sevkiyat Excel Raporunu İndir (Birim ve Toplam Fiyat Dahil) (.xls)",
            data=shipment_excel_data,
            file_name="detayli_sevkiyat_arsivi_fiyatli.xls",
            mime="application/vnd.ms-excel"
        )
        st.markdown("---")

        for idx, s_row in meta_ship_df.iterrows():
            with st.expander(f"İrsaliye: {s_row['IrsaliyeNo']} | Müşteri: {s_row['MusteriAdi']}"):
                col_s1, col_s2, col_s3 = st.columns([2, 1, 1])
                with col_s1:
                    st.markdown(f"**Müşteri:** {s_row['MusteriAdi']}")
                    st.markdown(f"**İrsaliye No:** {s_row['IrsaliyeNo']}")
                    st.markdown(f"**Açıklama / Not:** {s_row['Notlar']}")
                    
                    irs_kalemleri = tx_df[(tx_df["HareketTuru"] == "Çıkış") & (tx_df["Aciklama"].astype(str).str.contains(str(s_row['IrsaliyeNo'])))]
                    if not irs_kalemleri.empty:
                        toplam_irs_tutar = irs_kalemleri["ToplamTutar"].sum()
                        st.markdown(f"**Toplam Sevkiyat Tutarı:** `{toplam_irs_tutar:,.2f} TL`")
                        st.markdown("---")
                        st.markdown("**Sevk Edilen Kalemler:**")
                        for _, ik in irs_kalemleri.iterrows():
                            st.write(f"- {ik['StokKodu']} {ik['StokAdi']} | Miktar: {ik['Miktar']:,.2f} {ik['Birim']} | Birim Fiyat: {ik['BirimFiyat']:,.2f} TL | Tutar: {ik['ToplamTutar']:,.2f} TL")

                    if s_row['IlceTarimDocYolu'] and os.path.exists(str(s_row['IlceTarimDocYolu'])):
                        with open(s_row['IlceTarimDocYolu'], "rb") as doc_btn:
                            st.download_button(
                                label="📥 İlçe Tarım Evrakını İndir",
                                data=doc_btn,
                                file_name=os.path.basename(s_row['IlceTarimDocYolu']),
                                key=f"dl_ilce_tarim_{idx}"
                            )
                    else:
                        st.info("İlçe Tarım evrakı yüklenmemiş.")

                with col_s2:
                    st.markdown("**Sevkiyat Fotoğrafı**")
                    if s_row['SevkFotoYolu'] and os.path.exists(str(s_row['SevkFotoYolu'])):
                        st.image(s_row['SevkFotoYolu'], width=200)
                    else:
                        st.write("Sevkiyat fotoğrafı yok.")

                with col_s3:
                    st.markdown("**İlçe Tarım Belgesi Önizleme**")
                    if s_row['IlceTarimDocYolu'] and os.path.exists(str(s_row['IlceTarimDocYolu'])) and s_row['IlceTarimDocYolu'].lower().endswith(('png', 'jpg', 'jpeg')):
                        st.image(s_row['IlceTarimDocYolu'], width=200)
                    else:
                        st.write("Önizleme yapılamıyor (PDF/Doküman).")

                st.markdown("---")
                if st.button(f"🗑️ Bu Sevkiyatı (İrsaliye: {s_row['IrsaliyeNo']}) İptal Et & Sil", key=f"del_ship_{idx}"):
                    tx_df = load_data(STOCK_TRANSACTIONS_FILE, ["Tarih", "HareketTuru", "Depo", "StokKodu", "StokAdi", "Miktar", "Birim", "BirimFiyat", "ToplamTutar", "PartiNo", "Tedarikci", "Aciklama"])
                    irs_no = str(s_row['IrsaliyeNo']).strip()
                    sevk_mask = (tx_df["HareketTuru"] == "Çıkış") & (tx_df["Aciklama"].astype(str).str.contains(irs_no, regex=False))
                    silinen_sevk_hareketleri = tx_df[sevk_mask].copy()
                    silinen_sevk_meta = meta_ship_df[meta_ship_df["IrsaliyeNo"].astype(str) == irs_no].copy()
                    tx_df = tx_df[~sevk_mask]
                    save_data(tx_df, STOCK_TRANSACTIONS_FILE)
                    
                    meta_ship_df = meta_ship_df[meta_ship_df["IrsaliyeNo"].astype(str) != irs_no]
                    save_data(meta_ship_df, SHIPMENT_META_FILE)
                    audit_log("SILME", "SEVKIYAT", irs_no, old_value={
                        "hareketler": silinen_sevk_hareketleri.to_dict(orient="records"),
                        "meta": silinen_sevk_meta.to_dict(orient="records")
                    })
                    
                    st.success(f"✅ İrsaliye {irs_no} nolu sevkiyat silindi ve ürünler tekrar stoğa iade edildi!")
                    st.rerun()

# --- 7. İZLENEBİLİRLİK & İŞLEM GEÇMİŞİ ---
elif choice == "7. İzlenebilirlik & İşlem Geçmişi":
    st.header("🔎 Lot İzlenebilirliği & İşlem Geçmişi")
    tab_trace, tab_audit = st.tabs(["🔗 Lot / Üretim / Sevkiyat Zinciri", "🧾 Kullanıcı İşlem Geçmişi"])

    with tab_trace:
        tx_trace = load_data(STOCK_TRANSACTIONS_FILE, ["Tarih", "HareketTuru", "Depo", "StokKodu", "StokAdi", "Miktar", "Birim", "BirimFiyat", "ToplamTutar", "PartiNo", "Tedarikci", "Aciklama"])
        ship_trace = load_data(SHIPMENT_META_FILE, ["IrsaliyeNo", "MusteriAdi", "SevkFotoYolu", "IlceTarimDocYolu", "Notlar"])
        arama = st.text_input("Lot / parti, iş emri (mamul lotu) veya irsaliye numarası ara", placeholder="Örn: LOT-2026-15, URT-2026-041 veya IRS-2026-001").strip()

        if arama:
            # İrsaliye girildiyse önce sevk edilen mamul lotlarını bul.
            ship_meta_match = ship_trace[ship_trace["IrsaliyeNo"].astype(str).str.strip() == arama] if not ship_trace.empty else pd.DataFrame()
            if not ship_meta_match.empty:
                shipment_rows = tx_trace[(tx_trace["HareketTuru"] == "Çıkış") & tx_trace["Aciklama"].astype(str).str.contains(arama, regex=False)]
                hedef_mamul_lotlari = shipment_rows["PartiNo"].astype(str).str.strip().unique().tolist()
            else:
                shipment_rows = pd.DataFrame()
                hedef_mamul_lotlari = []

            # Arama bir hammadde lotu ise onu tüketen iş emirlerini bul.
            raw_usage = tx_trace[(tx_trace["HareketTuru"] == "Çıkış") & (tx_trace["PartiNo"].astype(str).str.strip() == arama) & tx_trace["Tedarikci"].astype(str).str.startswith("İş Emri:")]
            is_emirleri = []
            for val in raw_usage["Tedarikci"].astype(str).tolist():
                no = val.split("İş Emri:", 1)[1].strip()
                if no and no not in is_emirleri:
                    is_emirleri.append(no)

            # Arama doğrudan bir mamul lotu / iş emri ise zincire ekle.
            direct_mamul = tx_trace[(tx_trace["HareketTuru"] == "Giriş") & (tx_trace["Depo"] == "Mamül Deposu") & (tx_trace["PartiNo"].astype(str).str.strip() == arama)]
            if not direct_mamul.empty and arama not in is_emirleri:
                is_emirleri.append(arama)
            for lot in hedef_mamul_lotlari:
                if lot not in is_emirleri:
                    is_emirleri.append(lot)

            # İş emrinden geriye doğru hammadde lotlarını ve ileri doğru sevkiyatları topla.
            hammaddeler = []
            mamuller = []
            sevkiyatlar = []
            for is_no in is_emirleri:
                sarflar = tx_trace[(tx_trace["HareketTuru"] == "Çıkış") & (tx_trace["Tedarikci"].astype(str).str.strip() == f"İş Emri: {is_no}")]
                for _, r in sarflar.iterrows():
                    hammaddeler.append(r.to_dict())
                mamul_rows = tx_trace[(tx_trace["HareketTuru"] == "Giriş") & (tx_trace["Depo"] == "Mamül Deposu") & (tx_trace["PartiNo"].astype(str).str.strip() == is_no)]
                for _, r in mamul_rows.iterrows():
                    mamuller.append(r.to_dict())
                sevk_rows = tx_trace[(tx_trace["HareketTuru"] == "Çıkış") & (tx_trace["Depo"] == "Mamül Deposu") & (tx_trace["PartiNo"].astype(str).str.strip() == is_no) & tx_trace["Tedarikci"].astype(str).str.startswith("Müşteri Sevkiyat:")]
                for _, r in sevk_rows.iterrows():
                    rec = r.to_dict()
                    rec["Musteri"] = str(r["Tedarikci"]).split("Müşteri Sevkiyat:", 1)[1].strip()
                    acik = str(r["Aciklama"])
                    rec["IrsaliyeNo"] = acik.split("İrsaliye:", 1)[1].split(".", 1)[0].strip() if "İrsaliye:" in acik else ""
                    sevkiyatlar.append(rec)

            # Arama yalnızca mevcut bir hammadde lotuysa giriş bilgisini de göster.
            hammadde_giris = tx_trace[(tx_trace["HareketTuru"] == "Giriş") & (tx_trace["PartiNo"].astype(str).str.strip() == arama)]
            if not raw_usage.empty or is_emirleri or not ship_meta_match.empty or not hammadde_giris.empty:
                st.success("İzlenebilirlik kaydı bulundu.")
                if not hammadde_giris.empty and arama not in is_emirleri:
                    st.subheader("1️⃣ Hammadde / Giriş Lotu")
                    st.dataframe(hammadde_giris[["Tarih","StokKodu","StokAdi","PartiNo","Tedarikci","Miktar","Birim"]], use_container_width=True, hide_index=True)
                if hammaddeler:
                    st.subheader("1️⃣ Kullanılan Hammadde Lotları")
                    hdf = pd.DataFrame(hammaddeler)
                    st.dataframe(hdf[["Tarih","StokKodu","StokAdi","PartiNo","Tedarikci","Miktar","Birim"]], use_container_width=True, hide_index=True)
                if is_emirleri:
                    st.subheader("2️⃣ Üretim İş Emri / Mamul Lotu")
                    st.write(" → ".join(is_emirleri))
                if mamuller:
                    mdf = pd.DataFrame(mamuller)
                    st.dataframe(mdf[["Tarih","StokKodu","StokAdi","PartiNo","Miktar","Birim"]], use_container_width=True, hide_index=True)
                if sevkiyatlar:
                    st.subheader("3️⃣ Müşteri / İrsaliye / Sevkiyat")
                    sdf = pd.DataFrame(sevkiyatlar)
                    st.dataframe(sdf[["Tarih","StokKodu","StokAdi","PartiNo","Musteri","IrsaliyeNo","Miktar","Birim"]], use_container_width=True, hide_index=True)
                else:
                    st.info("Bu zincire bağlı müşteri sevkiyatı henüz bulunmuyor.")
            else:
                st.warning("Bu numarayla eşleşen lot, iş emri veya irsaliye bulunamadı.")
        else:
            st.info("Bir lot, iş emri veya irsaliye numarası girerek uçtan uca izlenebilirliği görüntüleyebilirsin.")

    with tab_audit:
        audit_df = load_audit_log(2000)
        if audit_df.empty:
            st.info("Henüz audit kaydı oluşmadı. Bu güncellemeden sonraki kritik işlemler burada görünecek.")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                user_filter = st.selectbox("Kullanıcı", ["Tümü"] + sorted(audit_df["username"].dropna().astype(str).unique().tolist()))
            with c2:
                type_filter = st.selectbox("İşlem alanı", ["Tümü"] + sorted(audit_df["entity_type"].dropna().astype(str).unique().tolist()))
            with c3:
                action_filter = st.selectbox("İşlem", ["Tümü"] + sorted(audit_df["action"].dropna().astype(str).unique().tolist()))
            view = audit_df.copy()
            if user_filter != "Tümü": view = view[view["username"] == user_filter]
            if type_filter != "Tümü": view = view[view["entity_type"] == type_filter]
            if action_filter != "Tümü": view = view[view["action"] == action_filter]
            display = view.rename(columns={"created_at":"Tarih/Saat","username":"Kullanıcı","action":"İşlem","entity_type":"Alan","entity_id":"Kayıt No"})
            st.dataframe(display[["Tarih/Saat","Kullanıcı","İşlem","Alan","Kayıt No"]], use_container_width=True, hide_index=True)
            st.markdown("### İşlem Detayı")
            detail_ids = view["id"].tolist()
            if detail_ids:
                selected_id = st.selectbox("Detayını görmek istediğin kayıt", detail_ids, format_func=lambda x: f"#{x}")
                drow = view[view["id"] == selected_id].iloc[0]
                dc1, dc2 = st.columns(2)
                with dc1:
                    st.markdown("**Önceki değer**")
                    try: st.json(json.loads(drow["old_value"]) if drow["old_value"] else {})
                    except Exception: st.code(str(drow["old_value"] or ""))
                with dc2:
                    st.markdown("**Yeni değer**")
                    try: st.json(json.loads(drow["new_value"]) if drow["new_value"] else {})
                    except Exception: st.code(str(drow["new_value"] or ""))
