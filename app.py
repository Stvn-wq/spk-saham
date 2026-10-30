import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# 1. untuk konfigurasi halaman dashboard
st.set_page_config(
    page_title="SPK Transaksi Saham Rule-Based",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("Sistem Pendukung Keputusan Rekomendasi Transaksi Saham")
st.caption("Implementasi Metode Rule-Based dengan Parameter Dinamis SMA & RSI | Objek Saham Blue Chip BEI")

# 2. panel mengontrol parameter di sidebar
st.sidebar.header("Panel Pengaturan Parameter")

# pilihan 3 saham blue chip
pilihan_saham = st.sidebar.selectbox(
    "Pilih Saham Blue Chip:",
    options=["BBCA.JK", "BBRI.JK", "TLKM.JK"],
    index=0,
    help="BBCA (Perbankan Swasta), BBRI (Perbankan BUMN), TLKM (Infrastruktur)"
)

# pemilihan rentang waktu (default 3 tahun: 1 Sep 2023 - 31 Agu 2026)
tgl_mulai = st.sidebar.date_input("Tanggal Mulai:", datetime(2023, 9, 1))
tgl_selesai = st.sidebar.date_input("Tanggal Selesai:", datetime(2026, 8, 31))

st.sidebar.markdown("---")
st.sidebar.subheader("Parameter Indikator Teknikal (Dinamis)")

# mengatur slider indikator
sma_periode = st.sidebar.slider("Periode SMA (Hari):", min_value=5, max_value=50, value=20, step=1)
rsi_periode = st.sidebar.slider("Periode RSI (Hari):", min_value=7, max_value=30, value=14, step=1)
rsi_oversold = st.sidebar.slider("Ambang Batas Jenuh Jual (Oversold):", min_value=10, max_value=40, value=30, step=1)
rsi_overbought = st.sidebar.slider("Ambang Batas Jenuh Beli (Overbought):", min_value=60, max_value=90, value=70, step=1)

tombol_proses = st.sidebar.button("Jalankan Analisis Keputusan", type="primary")

# 3. fungsi perhitungan matematis indikatornya
def hitung_indikator(df, periode_sma, periode_rsi):
    # perhitungan SMA
    df['SMA'] = df['Close'].rolling(window=periode_sma).mean()
    
    # Perhitungan RSI
    perubahan_harga = df['Close'].diff()
    gain = perubahan_harga.where(perubahan_harga > 0, 0.0)
    loss = -perubahan_harga.where(perubahan_harga < 0, 0.0)
    
    # rata-rata eksponensial
    avg_gain = gain.ewm(alpha=1/periode_rsi, min_periods=periode_rsi, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/periode_rsi, min_periods=periode_rsi, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df
 
# 4. mesin inferensi rule-based
def evaluasi_rule_based(harga_terakhir, sma_terakhir, rsi_terakhir, batas_bawah, batas_atas):
    # aturan 1 (R1): harga > SMA dan RSI <= batas bawah
    if harga_terakhir > sma_terakhir and rsi_terakhir <= batas_bawah:
        kode = "R1"
        status = "Bullish Correction (Oversold in Uptrend)"
        saran = "Harga terkoreksi di area jenuh jual saat tren naik. Disarankan mempertimbangkan aksi Akumulasi Beli (Buy on Weakness)."
        warna = "success"

    # aturan 2 (R2): harga > SMA dan RSI >= batas atas
    elif harga_terakhir > sma_terakhir and rsi_terakhir >= batas_atas:
        kode = "R2"
        status = "Bullish Overextended (Overbought in Uptrend)"
        saran = "Penguatan harga telah memasuki area jenuh beli. Disarankan mempertimbangkan aksi Jual Bertahap untuk Realisasi Keuntungan (Take Profit)."
        warna = "warning"

    # aturan 3 (R3): harga < SMA dan RSI >= batas atas
    elif harga_terakhir < sma_terakhir and rsi_terakhir >= batas_atas:
        kode = "R3"
        status = "Bearish Pullback (Overbought in Downtrend)"
        saran = "Kenaikan harga tertahan di area jenuh saat tren turun. Disarankan mempertimbangkan aksi Jual (Sell / Cut Loss) untuk membatasi risiko."
        warna = "error"

    # aturan 4 (R4): harga < SMA dan RSI <= batas bawah
    elif harga_terakhir < sma_terakhir and rsi_terakhir <= batas_bawah:
        kode = "R4"
        status = "Strong Bearish (Oversold in Downtrend)"
        saran = "Tekanan jual dominan pada tren turun. Disarankan Menunggu Konfirmasi Pasar (Wait and See) dan belum melakukan aksi beli."
        warna = "info"

    # Rule 5 (R5): Kondisi Momentum Netral
    else:
        kode = "R5"
        status = "Neutral Momentum"
        saran = "Pasar bergerak konsolidasi (sideways). Tidak ada sinyal transaksi (Wait and See) hingga konfirmasi arah tren terbentuk."
        warna = "secondary"

    return kode, status, saran, warna

# 5. eksekusi data dan tampilan dashboard
if tombol_proses or True:
    with st.spinner(f"Mengambil data historis {pilihan_saham} dari Yahoo Finance..."):
        # tarik data lewat yfinance
        df_mentah = yf.download(pilihan_saham, start=tgl_mulai, end=tgl_selesai)
        
        # penyesuaian kolom kalau MultiIndex
        if isinstance(df_mentah.columns, pd.MultiIndex):
            df_mentah.columns = df_mentah.columns.get_level_values(0)

    if df_mentah.empty:
        st.error("Data gagal diambil. Pastikan koneksi internet aktif dan rentang tanggal valid.")
    else:
        # hitung indikator
        df = hitung_indikator(df_mentah.copy(), sma_periode, rsi_periode)
        df_valid = df.dropna().copy()

        # ambil baris data penutupan terakhir (End of Day)
        data_terakhir = df_valid.iloc[-1]
        harga_close = float(data_terakhir['Close'])
        nilai_sma = float(data_terakhir['SMA'])
        nilai_rsi = float(data_terakhir['RSI'])
        tgl_terakhir = df_valid.index[-1].strftime('%d-%m-%Y')

        # jalankan penalaran rule-based
        kode_rule, status_pasar, saran_keputusan, tipe_warna = evaluasi_rule_based(
            harga_close, nilai_sma, nilai_rsi, rsi_oversold, rsi_overbought
        )

        # ringkasan nilai metrik
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Saham Terpilih", pilihan_saham.replace(".JK", ""))
        col2.metric("Harga Penutupan (Close)", f"Rp {harga_close:,.0f}", f"Per {tgl_terakhir}")
        col3.metric(f"Nilai SMA-{sma_periode}", f"Rp {nilai_sma:,.0f}", f"Posisi: {'Diatas' if harga_close > nilai_sma else 'Dibawah'} SMA")
        col4.metric(f"Nilai RSI-{rsi_periode}", f"{nilai_rsi:.2f}", f"Oversold ≤ {rsi_oversold} | Overbought ≥ {rsi_overbought}")

        st.markdown("---")

        # kotak saran deskriptif hasil keputusan
        st.subheader("Rekomendasi Keputusan Transaksi (Hasil Inferensi)")
        if tipe_warna == "success":
            st.success(f"**[{kode_rule}] Status: {status_pasar}**\n\n{saran_keputusan}")
        elif tipe_warna == "warning":
            st.warning(f"**[{kode_rule}] Status: {status_pasar}**\n\n{saran_keputusan}")
        elif tipe_warna == "error":
            st.error(f"**[{kode_rule}] Status: {status_pasar}**\n\n{saran_keputusan}")
        else:
            st.info(f"**[{kode_rule}] Status: {status_pasar}**\n\n{saran_keputusan}")

        # tabel data penutupan harian terakhir
        with st.expander("Lihat Riwayat Data Tabel Terakhir"):
            st.dataframe(df_valid[['Open', 'High', 'Low', 'Close', 'SMA', 'RSI', 'Volume']].tail(10))