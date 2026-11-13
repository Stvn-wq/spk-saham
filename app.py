from datetime import datetime, timedelta
import sqlite3
import pandas as pd
import streamlit as st
import yfinance as yf

# 1. halaman dashboard utama
st.set_page_config(
    page_title="SPK Transaksi Saham", layout="centered", initial_sidebar_state="collapsed"
)

# judul
st.markdown(
    "<h2 style='text-align: center; margin-bottom: 25px;'>Sistem Pendukung"
    " Keputusan Transaksi Saham</h2>",
    unsafe_allow_html=True,
)

# 2. penggunaan SQLite (untuk local cache)
def ambil_data_saham(ticker, start_date, end_date):
    nama_tabel = ticker.replace(".", "_")
    db_file = "saham.db"
    conn = sqlite3.connect(db_file)

    str_start = start_date.strftime("%Y-%m-%d")
    str_end = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")

    # keberadaan tabel SQLite
    query_cek = f"SELECT name FROM sqlite_master WHERE type='table' AND name='{nama_tabel}'"
    tabel_ada = pd.read_sql(query_cek, conn)

    # kalau tabel ada, periksa apakah rentang tanggalnya tersedia
    if not tabel_ada.empty:
      query_data = f"SELECT * FROM {nama_tabel} WHERE Date >= '{str_start}' AND Date < '{str_end}'"
      df_lokal = pd.read_sql(
          query_data, conn, index_col="Date", parse_dates=["Date"]
      )
      # ini kalau data riwayat lengkap di database, mencukupi periode indikator, dan mencakup akhir rentang tanggal (toleransi 4 hari libur bursa)
      if (
          not df_lokal.empty
          and len(df_lokal) >= 20
          and (end_date - df_lokal.index.max().date()).days <= 4
      ):
        conn.close()
        return df_lokal, "SQLite Lokal (Cache)"

    # kalau belum ada di basis data lokal, tarik dulu dari yahoo finance
    df_download = yf.download(
        ticker, start=start_date, end=str_end, progress=False
    )

    if isinstance(df_download.columns, pd.MultiIndex):
        df_download.columns = df_download.columns.get_level_values(0)

    if not df_download.empty:
        if df_download.index.tz is not None:
            df_download.index = df_download.index.tz_localize(None)

        # ambil kolom standar lalu simpan ke SQLite lokal
        kolom_standar = ["Open", "High", "Low", "Close", "Volume"]
        df_tersimpan = df_download[
            [col for col in kolom_standar if col in df_download.columns]
        ]
        df_tersimpan.to_sql(nama_tabel, conn, if_exists="replace", index=True)
        conn.close()
        return df_tersimpan, "Yahoo Finance"

    conn.close()
    return pd.DataFrame(), "Data Tidak Ditemukan"

# 3. perhitungan indikator teknikal
def hitung_indikator(df, periode_sma, periode_rsi):
    # simple moving average (sma)
    df["SMA"] = df["Close"].rolling(window=periode_sma).mean()

    # relative strength index (rsi)
    perubahan_harga = df["Close"].diff()
    gain = perubahan_harga.where(perubahan_harga > 0, 0.0)
    loss = -perubahan_harga.where(perubahan_harga < 0, 0.0)

    avg_gain = gain.ewm(
        alpha=1 / periode_rsi, min_periods=periode_rsi, adjust=False
    ).mean()
    avg_loss = loss.ewm(
        alpha=1 / periode_rsi, min_periods=periode_rsi, adjust=False
    ).mean()

    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))
    return df

# 4. rule-based (forward chaining)
def evaluasi_rule_based(
    harga_terakhir, sma_terakhir, rsi_terakhir, batas_bawah, batas_atas
):
    if harga_terakhir > sma_terakhir and rsi_terakhir <= batas_bawah:
        status = "Bullish Correction (Oversold in Uptrend)"
        saran = (
            "Harga terkoreksi di area jenuh jual saat tren naik. Disarankan"
            " mempertimbangkan aksi Akumulasi Beli (Buy on Weakness)."
        )
        warna = "success"
    elif harga_terakhir > sma_terakhir and rsi_terakhir >= batas_atas:
        status = "Bullish Overextended (Overbought in Uptrend)"
        saran = (
            "Penguatan harga telah memasuki area jenuh beli. Disarankan"
            " mempertimbangkan aksi Jual Bertahap untuk Realisasi Keuntungan"
            " (Take Profit)."
        )
        warna = "warning"
    elif harga_terakhir < sma_terakhir and rsi_terakhir >= batas_atas:
        status = "Bearish Pullback (Overbought in Downtrend)"
        saran = (
            "Kenaikan harga tertahan di area jenuh saat tren turun. Disarankan"
            " mempertimbangkan aksi Jual (Sell / Cut Loss) untuk membatasi"
            " risiko."
        )
        warna = "error"
    elif harga_terakhir < sma_terakhir and rsi_terakhir <= batas_bawah:
        status = "Strong Bearish (Oversold in Downtrend)"
        saran = (
            "Tekanan jual dominan pada tren turun. Disarankan Menunggu"
            " Konfirmasi Pasar (Wait and See) dan belum melakukan aksi beli."
        )
        warna = "info"
    else:
        status = "Neutral Momentum"
        saran = (
            "Pasar bergerak konsolidasi (sideways). Tidak ada sinyal transaksi"
            " (Wait and See) hingga konfirmasi arah tren terbentuk."
        )
        warna = "info"

    return status, saran, warna

# 5. pemilihan untuk user
# Pilihan Saham
pilihan_saham = st.selectbox(
    "Pilih saham:", options=["BBCA.JK", "BBRI.JK", "TLKM.JK"], index=0,
    filter_mode=None, # menonaktifkan keyboard, jadi user g bisa ketik cuman bisa klik
)

# rentang waktu
from datetime import timedelta

batas_tertua = datetime(2004, 10, 1).date()
hari_ini = datetime.now().date()

col_tgl1, col_tgl2 = st.columns(2)
with col_tgl1:
  tgl_mulai = st.date_input(
      "Tanggal Mulai:",
      value=datetime(2023, 9, 1).date(),
      min_value=batas_tertua,
      max_value=hari_ini,
  )

# kunci batas tanggal selesai pas 3 tahun dari tanggal mulai
maks_tgl_selesai = min(hari_ini, tgl_mulai + timedelta(days=1095))

with col_tgl2:
  # nilai default dan batas maksimalnya otomatis ikut maks_tgl_selesai
  tgl_selesai = st.date_input(
      "Tanggal Selesai:",
      value=maks_tgl_selesai,
      min_value=tgl_mulai,
      max_value=maks_tgl_selesai,
  )

selisih_hari = (tgl_selesai - tgl_mulai).days

# keterangan rentang waktu
if selisih_hari < 30:
  st.caption(
      "Peringatan: Rentang waktu minimal 30 hari kalender agar indikator dapat"
      " dihitung."
  )
else:
  st.caption(f"Rentang waktu: {selisih_hari} hari (maksimal hanya 3 tahun)")

st.markdown("<br>", unsafe_allow_html=True)

# parameter indikator teknikal
st.markdown("##### Parameter indikator teknikal")
col_sma, col_rsi = st.columns(2)
with col_sma:
  sma_periode = st.slider(
      "Periode SMA (Hari):", min_value=5, max_value=50, value=20, step=1
  )
with col_rsi:
  rsi_periode = st.slider(
      "Periode RSI (Hari):", min_value=7, max_value=30, value=14, step=1
  )

col_os, col_ob = st.columns(2)
with col_os:
  rsi_oversold = st.slider(
      "Ambang batas jenuh jual (oversold):",
      min_value=10,
      max_value=40,
      value=30,
      step=1,
  )
with col_ob:
  rsi_overbought = st.slider(
      "Ambang batas jenuh beli (overbought):",
      min_value=60,
      max_value=90,
      value=70,
      step=1,
  )

st.markdown("<br>", unsafe_allow_html=True)

# tombol mulai analisis
tombol_analisis = st.button("Mulai analisis", type="primary", use_container_width=True)

# 6. hasil keputusan (muncul pas tombol diklik aja)
if tombol_analisis:
    if selisih_hari < 30:
        st.error(
            "Gagal memproses: Rentang tanggal tidak valid. Pastikan rentang"
            " waktu minimal 30 hari."
        )
    else:
        with st.spinner("Memproses data pasar dan mengevaluasi aturan..."):
            df_mentah, sumber_data = ambil_data_saham(
                pilihan_saham, tgl_mulai, tgl_selesai
            )

        if df_mentah.empty:
            st.error(
                "Data perdagangan tidak ditemukan untuk rentang tanggal"
                " tersebut. Pastikan bursa aktif pada tanggal yang dipilih."
            )
        else:
            # hitung sma dan rsi
            df_indikator = hitung_indikator(
                df_mentah.copy(), sma_periode, rsi_periode
            )
            df_valid = df_indikator.dropna().copy()

            if df_valid.empty:
                st.warning(
                    f"Data perdagangan yang tercatat pada rentang ini hanya ada"
                    f" {len(df_mentah)} baris, sehingga tidak mencukupi untuk"
                    f" menghitung indikator periode SMA-{sma_periode} (memerlukan"
                    f" minimal {sma_periode} baris data). Perpanjang rentang"
                    " tanggal observasi."
                )
            else:
                # ambil data hari terakhir
                baris_terakhir = df_valid.iloc[-1]
                harga_close = float(baris_terakhir["Close"])
                nilai_sma = float(baris_terakhir["SMA"])
                nilai_rsi = float(baris_terakhir["RSI"])
                tgl_terakhir = df_valid.index[-1].strftime("%d-%m-%Y")

                # eksekusi rule-based
                status_pasar, saran_keputusan, tipe_warna = evaluasi_rule_based(
                    harga_close,
                    nilai_sma,
                    nilai_rsi,
                    rsi_oversold,
                    rsi_overbought,
                )

                st.markdown("---")

                # kartu ringkasan metriknya
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                col_m1.metric("Saham Terpilih", pilihan_saham.replace(".JK", ""))
                col_m2.metric(
                    "Harga Penutupan (Close)",
                    f"Rp {harga_close:,.0f}",
                    f"Per {tgl_terakhir}",
                )

                status_posisi_sma = (
                    "Di atas SMA" if harga_close > nilai_sma else "Di bawah SMA"
                )
                col_m3.metric(
                    f"Nilai SMA-{sma_periode}",
                    f"Rp {nilai_sma:,.0f}",
                    status_posisi_sma,
                )

                status_momentum = (
                    "Oversold"
                    if nilai_rsi <= rsi_oversold
                    else ("Overbought" if nilai_rsi >= rsi_overbought else "Netral")
                )
                col_m4.metric(
                    f"Nilai RSI-{rsi_periode}",
                    f"{nilai_rsi:.2f}",
                    f"Area {status_momentum}",
                )

                st.markdown("<br>", unsafe_allow_html=True)

                # kotak hasil rekomendasi
                st.markdown("##### Hasil rekomendasi:")
                pesan_rekomendasi = (
                    f"**Status Kondisi Pasar:** {status_pasar}\n\n"
                    f"**Saran Tindakan:** {saran_keputusan}"
                )

                if tipe_warna == "success":
                    st.success(pesan_rekomendasi)
                elif tipe_warna == "warning":
                    st.warning(pesan_rekomendasi)
                elif tipe_warna == "error":
                    st.error(pesan_rekomendasi)
                else:
                    st.info(pesan_rekomendasi)

                st.caption(f"Sumber Data: {sumber_data}")
                st.caption(
                    "Hasil rekomendasi ini merupakan analisis pendukung"
                    " keputusan berbasis data historis dan aturan logika"
                    " teknikal (Rule-Based), bukan jaminan mutlak pergerakan"
                    " pasar. Keputusan akhir transaksi tetap berada sepenuhnya"
                    " pada pertimbangan mandiri investor.")
