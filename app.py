import streamlit as st
import pandas as pd
from datetime import datetime
import os
from PIL import Image

st.set_page_config(page_title="THE DIŞ TİCARET - Üretim dan Stok Yönetimi", page_icon="🏭", layout="wide")

DB_DIR = "data"
PHOTO_DIR = os.path.join(DB_DIR, "production_photos")
SPEC_FILE_DIR = os.path.join(DB_DIR, "spec_files")
SPEC_PHOTO_DIR = os.path.join(DB_DIR, "spec_photos")

os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(PHOTO_DIR, exist_ok=True)
os.makedirs(SPEC_FILE_DIR, exist_ok=True)
os.makedirs(SPEC_PHOTO_DIR, exist_ok=True)

MASTER_ITEMS_FILE = os.path.join(DB_DIR, "master_items.csv")
STOCK_TRANSACTIONS_FILE = os.path.join(DB_DIR, "stock_transactions.csv")
PRODUCTION_META_FILE = os.path.join(DB_DIR, "production_meta.csv")
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
        except Exception:
            return pd.DataFrame(columns=columns)
    return pd.DataFrame(columns=columns)

def save_data(df, filepath):
    df.to_csv(filepath, index=False)

st.title("THE DIŞ TİCARET - ERP Stok ve Üretim Yönetim Sistemi")
st.markdown("Üretim föyü düzenleme ekranı tüm kalemleri (sarfiyat ve fireler dahil) içerecek şekilde güncellendi canım! ✨")

menu = [
    "1. Stok Kartı Tanımlama", 
    "2. Depo / Malzeme Girişi", 
    "3. Cari dan Ürün Spek Yönetimi",
    "4. Üretime Sevk / Reçeteli Üretim ve Maliyet",
    "5. Stok Durumu, Hareket Panosu ve Föy Düzenleme"
]
choice = st.sidebar.radio("📋 ERP Modülleri", menu)

st.sidebar.markdown("---")
if st.sidebar.button("🧹 Tüm Verileri Sıfırla / Temizle"):
    for f_path in [MASTER_ITEMS_FILE, STOCK_TRANSACTIONS_FILE, PRODUCTION_META_FILE, CARILER_FILE, SPEK_FILE]:
        if os.path.exists(f_path):
            os.remove(f_path)
    st.sidebar.success("Tüm veriler sıfırlandı! Sayfayı yenileyebilirsin.")
    st.rerun()

# --- 1. STOK KARTI TANIMLAMA ---
if choice == "1. Stok Kartı Tanımlama":
    st.header("🗂️ Yeni Stok Kartı Tanımlama")
    
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
                st.error("Stok kodu ve stok adı zorunludur!")
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

    st.subheader("📋 Sistemde Tanımlı Stok Kartları")
    master_df = load_data(MASTER_ITEMS_FILE, ["StokKodu", "StokAdi", "Depo", "Birim"])
    if master_df.empty:
        st.info("Henüz sistemde hiç stok kartı yok.")
    else:
        st.dataframe(master_df, use_container_width=True)

# --- 2. DEPO / MALZEME GİRİŞİ ---
elif choice == "2. Depo / Malzeme Girişi":
    st.header("📥 Depo Malzeme Kabul (Giriş Fişi)")
    
    master_df = load_data(MASTER_ITEMS_FILE, ["StokKodu", "StokAdi", "Depo", "Birim"])
    
    if master_df.empty:
        st.error("🚨 Sistemde tanımlı stok kartı yok! Önce '1. Stok Kartı Tanımlama' modülünden kart açmalısın.")
    else:
        with st.form("stock_in_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                g_tarih = st.date_input("Giriş Tarihi", datetime.now())
                
                item_options = [f"{row['StokKodu']} - {row['StokAdi']}" for _, row in master_df.iterrows()]
                selected_item_str = st.selectbox("Ürün Seçimi", item_options)
                
                hedef_depo = st.selectbox("Malzemenin Gireceği Depo", [
                    "Soğuk Hava Deposu", 
                    "Yardımcı Malzeme Deposu", 
                    "Yarı Mamül Deposu", 
                    "Mamül Deposu"
                ])
                
                miktar = st.number_input("Giriş Miktarı", min_value=0.01, step=1.0, format="%.2f")
            with col2:
                birim_fiyat = st.number_input("Birim Fiyat (TL) *Zorunlu*", min_value=0.01, step=0.01, value=1.0, format="%.2f")
                parti_no = st.text_input("Parti / Lot Numarası *Zorunlu*")
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
                    selected_code = selected_item_str.split(" - ")[0]
                    item_row = master_df[master_df["StokKodu"] == selected_code].iloc[0]
                    
                    new_tx = pd.DataFrame([{
                        "Tarih": str(g_tarih),
                        "HareketTuru": "Giriş",
                        "Depo": hedef_depo,
                        "StokKodu": item_row["StokKodu"],
                        "StokAdi": item_row["StokAdi"],
                        "Birim": item_row["Birim"],
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
                    st.success(f"Depo girişi başarıyla işlendi! ({hedef_depo} - Parti No: {parti_no})")

    st.subheader("📑 Son Yapılan Depo Giriş Hareketleri")
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

# --- 3. CARİ VE ÜRÜN SPEK YÖNETİMİ ---
elif choice == "3. Cari dan Ürün Spek Yönetimi":
    st.header("🤝 Cari Hesap ve Müşteri Özel Spek Tanımlama")
    
    tab1, tab2 = st.tabs(["Cari Tanımlama", "Cari Ürün & Spek Tanımları"])
    
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
                    
        st.subheader("Kayıtlı Cariler")
        df_cariler = load_data(CARILER_FILE, ["CariKodu", "CariAdi", "CariTipi"])
        if df_cariler.empty:
            st.info("Henüz kayıtlı cari bulunmuyor.")
        else:
            st.dataframe(df_cariler, use_container_width=True)

    with tab2:
        st.subheader("Cari Bazlı Ürün Spekleri, Dokümanları ve Ürün Fotoğrafları Tanımla")
        df_cariler = load_data(CARILER_FILE, ["CariKodu", "CariAdi", "CariTipi"])
        master_df = load_data(MASTER_ITEMS_FILE, ["StokKodu", "StokAdi", "Depo", "Birim"])
        
        if df_cariler.empty:
            st.warning("Önce 'Cari Tanımlama' sekmesinden bir cari eklemelisin!")
        elif master_df.empty:
            st.warning("Sistemde kayıtlı stok kartı bulunmuyor.")
        else:
            with st.form("spek_form", clear_on_submit=True):
                secilen_cari = st.selectbox("Firma (Cari) Seç", df_cariler['CariAdi'].tolist())
                urun_opts = [f"{row['StokKodu']} - {row['StokAdi']}" for _, row in master_df.iterrows()]
                secilen_stok_str = st.selectbox("İlgili Ürün Stok Seçimi", urun_opts)
                
                spek_adi = st.text_input("Spek Başlığı / Belge Adı (Örn: Müşteri Teknik Spek Dokümanı v1)")
                spek_detayi = st.text_area("Spek Detay / Özel İstekler (Örn: 28-30°Bx, 5kg Teneke Kutu, Laklı Kapak)")
                
                st.markdown("---")
                col_up1, col_up2 = st.columns(2)
                with col_up1:
                    uploaded_spek_file = st.file_uploader("📄 Spek Dosyası Yükle (PDF, Word vb.)", type=["pdf", "docx", "doc", "txt", "xlsx", "png", "jpg"])
                with col_up2:
                    uploaded_urun_foto = st.file_uploader("📸 Bu Spek'e Uygun Ürün / Numune Fotoğrafı", type=["png", "jpg", "jpeg"])

                spek_kaydet = st.form_submit_button("Spek ve Dosyaları Kaydet")
                
                if spek_kaydet and secilen_cari:
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
                    st.success("Ürün speki, dokümanı ve uygun ürün fotoğrafı başarıyla kaydedildi!")

            st.subheader("📋 Kayıtlı Cari Spek Listesi, Dokümanlar ve Ürün Görselleri")
            df_speks = load_data(SPEK_FILE, ["CariAdi", "StokKodu", "SpekAdi", "SpekDetayi", "SpekDosyaYolu", "UrunFotoYolu"])
            
            if df_speks.empty:
                st.info("Henüz girilmiş özel spek bulunmuyor.")
            else:
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

# --- 4. ÜRETIME SEVK / REÇETELİ ÜRETİM VE MALİYET ---
elif choice == "4. Üretime Sevk / Reçeteli Üretim ve Maliyet":
    st.header("📤 Dinamik Reçeteli Üretim, FIFO Sarfiyat, 2. Kalite Fire Girişi ve Föy")
    
    tx_df = load_data(STOCK_TRANSACTIONS_FILE, ["Tarih", "HareketTuru", "Depo", "StokKodu", "StokAdi", "Miktar", "Birim", "BirimFiyat", "ToplamTutar", "PartiNo", "Tedarikci", "Aciklama"])
    master_df = load_data(MASTER_ITEMS_FILE, ["StokKodu", "StokAdi", "Depo", "Birim"])
    
    if tx_df.empty:
        st.warning("⚠️ Önce depoya hammadde/malzeme girişi yapmalısınız.")
    elif master_df.empty:
        st.error("🚨 Sistemde kayıtlı stok kartı bulunmuyor.")
    else:
        temp_df = tx_df.copy()
        temp_df["NetMiktar"] = temp_df.apply(lambda row: row["Miktar"] if row["HareketTuru"] == "Giriş" else -row["Miktar"], axis=1)
        stock_balances = temp_df.groupby(["StokKodu", "StokAdi", "Depo", "Birim"])["NetMiktar"].sum().reset_index()
        stock_balances = stock_balances[stock_balances["NetMiktar"] > 0]

        if stock_balances.empty:
            st.warning("⚠️ Depolarda sevk edilebilir stok kalmadı.")
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
                st.subheader("1️⃣ Üretilecek Mamül ve Fotoğraf Bilgisi")
                c1, c2, c3 = st.columns(3)
                with c1:
                    uretim_tarihi = st.date_input("Üretim Tarihi", datetime.now())
                with c2:
                    mamul_options = [f"{row['StokKodu']} - {row['StokAdi']} ({row['Depo']})" for _, row in master_df.iterrows()]
                    secilen_mamul_str = st.selectbox("Üretilen Mamül Seçimi", mamul_options)
                with c3:
                    uretilen_miktar = st.number_input("Üretilen Mamül Miktarı", min_value=0.01, step=1.0, format="%.2f")

                uploaded_photo = st.file_uploader("📸 Üretilen Ürüne Ait Fotoğraf / Kalite Kontrol Görseli Yükle", type=["png", "jpg", "jpeg"])

                st.markdown("---")
                st.subheader(f"2️⃣ Reçete / Kullanılacak Hammaddeler (Sarfiyat - Stoktan Düşen)")
                
                stok_options = [f"{row['StokKodu']} - {row['StokAdi']} ({row['Depo']}) [Kalan: {row['NetMiktar']:,.2f} {row['Birim']}]" for _, row in stock_balances.iterrows()]
                
                recete_secimleri = []
                for i in range(st.session_state.recete_satir_sayisi):
                    rc1, rc2 = st.columns([3, 1])
                    with rc1:
                        m_sec = st.selectbox(f"{i+1}. Sarf Malzemesi", ["Seçiniz..."] + stok_options, key=f"mat_{i}")
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
                    is_emri_no = st.text_input("İş Emri / Parti No *Zorunlu*", placeholder="Örn: URT-2026-001")
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
                    st.markdown(f"**💰 Toplam Personel ve Ek Gider:** `{toplam_iscilik_gideri:,.2f} TL`")

                aciklama = st.text_area("Üretim Notları / Açıklama")

                submitted = st.form_submit_button("Üretimi, Sarfiyatı, Fireyi ve Maliyeti Onayla")
                
                if submitted:
                    secilen_recete = [(m, a) for m, a in recete_secimleri if m != "Seçiniz..." and a > 0]
                    secilen_fireler = [(f, a, pr) for f, a, pr in fire_secimleri if f != "Seçiniz..." and a > 0]

                    if not is_emri_no.strip():
                        st.error("İş emri numarası zorunludur!")
                    elif uretilen_miktar <= 0:
                        st.error("Üretilen miktar sıfırdan büyük olmalıdır!")
                    elif not secilen_recete:
                        st.error("En az bir adet hammadde sarfiyatı seçmeli ve miktarını girmelisin!")
                    else:
                        yeni_hareketler = []
                        toplam_sarfiyat_maliyeti = 0.0
                        hata_olustu = False
                        
                        for secilen_sarf_str, sevk_miktari in secilen_recete:
                            s_kod = secilen_sarf_str.split(" - ")[0]
                            depo_adi = secilen_sarf_str.split("(")[1].split(")")[0]
                            
                            girisler = tx_df[(tx_df["StokKodu"] == s_kod) & (tx_df["Depo"] == depo_adi) & (tx_df["HareketTuru"] == "Giriş")].copy()
                            girisler["Tarih_dt"] = pd.to_datetime(girisler["Tarih"])
                            girisler = girisler.sort_values(by="Tarih_dt", ascending=True)
                            
                            kalan_sevk = sevk_miktari
                            
                            for idx, row in girisler.iterrows():
                                if kalan_sevk <= 0:
                                    break
                                p_no = str(row["PartiNo"])
                                cikan_toplam = tx_df[(tx_df["StokKodu"] == s_kod) & (tx_df["PartiNo"].astype(str) == p_no) & (tx_df["HareketTuru"] == "Çıkış")]["Miktar"].sum()
                                parti_kalan = row["Miktar"] - cikan_toplam
                                
                                if parti_kalan > 0:
                                    dusulecek_miktar = min(kalan_sevk, parti_kalan)
                                    tutar = dusulecek_miktar * row["BirimFiyat"]
                                    toplam_sarfiyat_maliyeti += tutar
                                    
                                    yeni_hareketler.append({
                                        "Tarih": str(uretim_tarihi),
                                        "HareketTuru": "Çıkış",
                                        "Depo": depo_adi,
                                        "StokKodu": s_kod,
                                        "StokAdi": row["StokAdi"],
                                        "Birim": row["Birim"],
                                        "Miktar": dusulecek_miktar,
                                        "BirimFiyat": row["BirimFiyat"],
                                        "ToplamTutar": tutar,
                                        "PartiNo": p_no,
                                        "Tedarikci": f"İş Emri: {is_emri_no.strip()}",
                                        "Aciklama": f"Üretime Sarf. {aciklama}"
                                    })
                                    kalan_sevk -= dusulecek_miktar

                            if kalan_sevk > 0:
                                st.error(f"⚠️ **{secilen_sarf_str}** için depoda yeterli stok yok! Eksik miktar: **{kalan_sevk:,.2f}**")
                                hata_olustu = True
                                break

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
                            
                            st.success(f"🎉 Üretim föyü, sarfiyatlar ve 2. kalite fire girişleri başarıyla kaydedildi!")
                            st.info(f"📊 **Maliyet Özeti:** Sarfiyat: {toplam_sarfiyat_maliyeti:,.2f} TL | İşçilik & Gider: {toplam_iscilik_gideri:,.2f} TL | Fire Mahsubu: -{toplam_fire_maliyeti:,.2f} TL | **Net Üretim Maliyeti:** {toplam_uretim_maliyeti:,.2f} TL | **Birim Maliyet:** {mamul_birim_maliyet:,.2f} TL")

# --- 5. STOK DURUMU VE HAREKET PANOSU ---
elif choice == "5. Stok Durumu, Hareket Panosu ve Föy Düzenleme":
    st.header("📊 Stok Durumu, Hareket Panosu, Üretim İptali ve Föy Düzenleme")
    
    tx_df = load_data(STOCK_TRANSACTIONS_FILE, ["Tarih", "HareketTuru", "Depo", "StokKodu", "StokAdi", "Miktar", "Birim", "BirimFiyat", "ToplamTutar", "PartiNo", "Tedarikci", "Aciklama"])
    meta_df = load_data(PRODUCTION_META_FILE, ["IsEmriNo", "CalismaSaati", "IscilikGideri", "FotografYolu", "Notlar"])
    master_df = load_data(MASTER_ITEMS_FILE, ["StokKodu", "StokAdi", "Depo", "Birim"])
    
    if tx_df.empty:
        st.info("Henüz sistemde hiç hareket bulunmuyor.")
    else:
        st.subheader("📝 Kayıtlı Üretim Föyleri (İş Emirleri) Yönetimi & Tam Kalem Düzenleme")
        uretim_kayitlari = tx_df[(tx_df["Tedarikci"] == "Dahili Üretim") | (tx_df["Depo"] == "Mamül Deposu") & (tx_df["HareketTuru"] == "Giriş")]
        
        if not uretim_kayitlari.empty:
            is_emri_secenekleri = uretim_kayitlari["PartiNo"].astype(str).unique().tolist()
            secilen_is_emri = st.selectbox("İşlemi Yönetmek / Düzenlemek İstediğin İş Emri / Parti No", is_emri_secenekleri)
            
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

                st.markdown(f"### ⚙️ '{secilen_is_emri}' Nolu Föyü ve Tüm Kalemlerini Güncelle")
                
                with st.form(f"edit_full_form_{secilen_is_emri}"):
                    st.subheader("1️⃣ Üretilen Mamül Miktarı")
                    yeni_uretim_miktari = st.number_input("Güncellenmiş Üretim Miktarı", min_value=0.01, value=float(mamul_satir["Miktar"]), step=1.0, format="%.2f")

                    st.markdown("---")
                    st.subheader("2️⃣ Hammadde Sarfiyat Kalemleri Güncelleme")
                    st.info("Bu iş emrine ait mevcut sarfiyat kalemleri aşağıdadır. Yeni sarfiyat miktarlarını güncelleyebilir veya ekleyebilirsin.")

                    temp_df_b = tx_df.copy()
                    temp_df_b["NetMiktar"] = temp_df_b.apply(lambda r: r["Miktar"] if r["HareketTuru"] == "Giriş" else -r["Miktar"], axis=1)
                    stock_b_bal = temp_df_b.groupby(["StokKodu", "StokAdi", "Depo", "Birim"])["NetMiktar"].sum().reset_index()
                    stock_b_bal = stock_b_bal[stock_b_bal["NetMiktar"] > 0]
                    stok_options_edit = [f"{row['StokKodu']} - {row['StokAdi']} ({row['Depo']})" for _, row in master_df.iterrows()]

                    edit_sarf_secimleri = []
                    satir_sayisi_edit = max(4, len(mevcut_sarfiyatlar) + 2)
                    
                    for i in range(satir_sayisi_edit):
                        default_mat = "Seçiniz..."
                        default_val = 0.0
                        if i < len(mevcut_sarfiyatlar):
                            row_s = mevcut_sarfiyatlar.iloc[i]
                            match_str = f"{row_s['StokKodu']} - {row_s['StokAdi']} ({row_s['Depo']})"
                            if match_str in stok_options_edit or any(match_str in opt for opt in stok_options_edit):
                                default_mat = match_str
                            default_val = float(row_s["Miktar"])

                        rc1, rc2 = st.columns([3, 1])
                        with rc1:
                            m_sec_ed = st.selectbox(f"Sarf Malzemesi {i+1}", ["Seçiniz..."] + stok_options_edit, index=stok_options_edit.index(default_mat)+1 if default_mat in stok_options_edit else 0, key=f"edit_mat_{secilen_is_emri}_{i}")
                        with rc2:
                            m_amt_ed = st.number_input(f"Miktar {i+1}", min_value=0.0, value=default_val, step=1.0, format="%.2f", key=f"edit_amt_{secilen_is_emri}_{i}")
                        edit_sarf_secimleri.append((m_sec_ed, m_amt_ed))

                    st.markdown("---")
                    st.subheader("3️⃣ 2. Kalite / Fire Kalemleri")
                    edit_fire_secimleri = []
                    fire_satir_sayisi_edit = max(2, len(mevcut_fireler) + 1)
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
                        guncelle_pressed = st.form_submit_button("💾 Üretim Föyünü ve Tüm Kalemleri Güncelle")
                    with col_btn2:
                        sil_pressed = st.form_submit_button("🗑️ Üretimi Tamamen İptal Et & Sil")

                    if sil_pressed:
                        mask_mamul = (tx_df["PartiNo"].astype(str) == str(secilen_is_emri)) & (tx_df["Tedarikci"] == "Dahili Üretim")
                        mask_sarf_fire = tx_df["Tedarikci"].astype(str).str.contains(str(secilen_is_emri)) | (tx_df["PartiNo"].astype(str) == f"{secilen_is_emri}-FIRE")
                        tx_df = tx_df[~(mask_mamul | mask_sarf_fire)]
                        save_data(tx_df, STOCK_TRANSACTIONS_FILE)
                        st.success(f"✅ '{secilen_is_emri}' nolu iş emri silindi ve tüm hareketler iptal edildi!")
                        st.rerun()

                    if guncelle_pressed:
                        secilen_yeni_recete = [(m, a) for m, a in edit_sarf_secimleri if m != "Seçiniz..." and a > 0]
                        secilen_yeni_fireler = [(f, a, pr) for f, a, pr in edit_fire_secimleri if f != "Seçiniz..." and a > 0]

                        if yeni_uretim_miktari <= 0:
                            st.error("Üretilen miktar sıfırdan büyük olmalıdır!")
                        elif not secilen_yeni_recete:
                            st.error("En az bir adet hammadde sarfiyatı seçilmelidir!")
                        else:
                            mask_mamul_eski = (tx_df["PartiNo"].astype(str) == str(secilen_is_emri)) & (tx_df["Tedarikci"] == "Dahili Üretim")
                            mask_sarf_eski = tx_df["Tedarikci"].astype(str).str.contains(str(secilen_is_emri))
                            mask_fire_eski = tx_df["PartiNo"].astype(str) == f"{secilen_is_emri}-FIRE"
                            tx_df = tx_df[~(mask_mamul_eski | mask_sarf_eski | mask_fire_eski)]

                            yeni_eklenen_hareketler = []
                            toplam_sarfiyat_maliyeti = 0.0
                            hata_olustu_ed = False

                            for secilen_sarf_str, sevk_miktari in secilen_yeni_recete:
                                s_kod = secilen_sarf_str.split(" - ")[0]
                                depo_adi = secilen_sarf_str.split("(")[1].split(")")[0]

                                girisler = tx_df[(tx_df["StokKodu"] == s_kod) & (tx_df["Depo"] == depo_adi) & (tx_df["HareketTuru"] == "Giriş")].copy()
                                girisler["Tarih_dt"] = pd.to_datetime(girisler["Tarih"])
                                girisler = girisler.sort_values(by="Tarih_dt", ascending=True)

                                kalan_sevk = sevk_miktari
                                for idx, row in girisler.iterrows():
                                    if kalan_sevk <= 0:
                                        break
                                    p_no = str(row["PartiNo"])
                                    cikan_toplam = tx_df[(tx_df["StokKodu"] == s_kod) & (tx_df["PartiNo"].astype(str) == p_no) & (tx_df["HareketTuru"] == "Çıkış")]["Miktar"].sum()
                                    parti_kalan = row["Miktar"] - cikan_toplam

                                    if parti_kalan > 0:
                                        dusulecek_miktar = min(kalan_sevk, parti_kalan)
                                        tutar = dusulecek_miktar * row["BirimFiyat"]
                                        toplam_sarfiyat_maliyeti += tutar

                                        yeni_eklenen_hareketler.append({
                                            "Tarih": mamul_satir["Tarih"],
                                            "HareketTuru": "Çıkış",
                                            "Depo": depo_adi,
                                            "StokKodu": s_kod,
                                            "StokAdi": row["StokAdi"],
                                            "Birim": row["Birim"],
                                            "Miktar": dusulecek_miktar,
                                            "BirimFiyat": row["BirimFiyat"],
                                            "ToplamTutar": tutar,
                                            "PartiNo": p_no,
                                            "Tedarikci": f"İş Emri: {str(secilen_is_emri).strip()}",
                                            "Aciklama": f"Üretime Sarf (Güncellendi). {yeni_not}"
                                        })
                                        kalan_sevk -= dusulecek_miktar

                                if kalan_sevk > 0:
                                    st.error(f"⚠️ **{secilen_sarf_str}** için depoda yeterli stok yok! Eksik miktar: **{kalan_sevk:,.2f}**")
                                    hata_olustu_ed = True
                                    break

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

                                st.success(f"✨ '{secilen_is_emri}' nolu üretim föyü and tüm hammadde/fire kalemleri başarıyla güncellendi!")
                                st.rerun()

        else:
            st.info("Sistemde düzenlenebilecek kayıtlı bir dahili üretim bulunmuyor.")

        st.markdown("---")

        depo_listesi = ["Tümü"] + list(tx_df["Depo"].unique())
        secilen_depo_filtre = st.selectbox("📂 Depo Filtrele", depo_listesi)
        
        if secilen_depo_filtre != "Tümü":
            fiyat_hesap_df = tx_df[(tx_df["Depo"] == secilen_depo_filtre) & (tx_df["HareketTuru"] == "Giriş")]
        else:
            fiyat_hesap_df = tx_df[tx_df["HareketTuru"] == "Giriş"]
            
        toplam_envanter_maliyeti = fiyat_hesap_df["ToplamTutar"].sum() if not fiyat_hesap_df.empty else 0.0
        
        st.markdown("---")
        col_kpi1, col_kpi2 = st.columns(2)
        with col_kpi1:
            depo_etiketi = secilen_depo_filtre if secilen_depo_filtre != "Tümü" else "Tüm Depolar"
            st.metric(label=f"💰 Seçilen Alan Toplam Giriş Maliyeti ({depo_etiketi})", value=f"{toplam_envanter_maliyeti:,.2f} TL")
        with col_kpi2:
            toplam_islem_adedi = len(fiyat_hesap_df)
            st.metric(label="📦 Toplam Giriş Fişi / Lot Sayısı", value=f"{toplam_islem_adedi:,} Adet")
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
            
            csv_data = summary_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Güncel Stok Raporunu İndir (CSV)",
                data=csv_data,
                file_name=f"stok_durumu_{secilen_depo_filtre}.csv",
                mime="text/csv"
            )
        
        st.markdown("---")
        st.subheader("🔍 Ürün Bazlı Tüm Parti Girişleri ve Hareket Dökümü")
        
        if secilen_depo_filtre != "Tümü":
            secilebilir_urunler_df = global_summary_df[global_summary_df["Depo"] == secilen_depo_filtre]
        else:
            secilebilir_urunler_df = global_summary_df.copy()

        if not secilebilir_urunler_df.empty:
            urun_secenekleri = (secilebilir_urunler_df["Stok Kodu"] + " - " + secilebilir_urunler_df["Stok Adı"] + " (" + secilebilir_urunler_df["Depo"] + ")").tolist()
            secilen_urun_str = st.selectbox("İncelemek and Tüm Partilerini Görmek İstediğin Ürünü Seç", urun_secenekleri)
            
            if secilen_urun_str:
                s_kod = secilen_urun_str.split(" - ")[0]
                d_adi = secilen_urun_str.split("(")[1].split(")")[0]
                
                if "StKodu" in tx_df.columns:
                    urun_tum_hareketleri = tx_df[tx_df["StKodu"] == s_kod]
                else:
                    urun_tum_hareketleri = tx_df[(tx_df["StokKodu"] == s_kod) & (tx_df["Depo"] == d_adi)]
                
                st.markdown(f"**{secilen_urun_str}** ürününün sisteme yapılan **tüm parti girişleri and hareketleri**:")
                
                styled_hareketler = urun_tum_hareketleri.style.format({
                    "Miktar": "{:,.2f}",
                    "BirimFiyat": "{:,.2f} TL",
                    "ToplamTutar": "{:,.2f} TL"
                }, na_rep="")
                st.dataframe(styled_hareketler, use_container_width=True)
        else:
            st.info("Seçilebilir ürün bulunmuyor.")