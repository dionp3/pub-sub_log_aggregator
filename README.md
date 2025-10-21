Tentu. Berdasarkan kode sumber, *unit tests* yang sudah lulus, dan implementasi Docker Compose (Bonus) Anda, berikut adalah *file* **`README.md`** yang diperbarui secara detail, siap untuk *submission*.

-----

# Pub-Sub Log Aggregator dengan Idempotent Consumer dan Deduplikasi

## Deskripsi Proyek

Layanan ini mengimplementasikan Log Aggregator berbasis pola **Publish-Subscribe**. Sistem dirancang untuk menangani *at-least-once delivery* dari *publisher* dengan menjamin **exactly-once processing** melalui **Idempotent Consumer** dan **Durable Deduplication Store (SQLite)** yang persisten di dalam *container* Docker.

## Struktur Proyek

```
pub-sub_log_aggregator/
├── src/
│   ├── main.py         # Logika Aggregator & FastAPI Endpoints
│   ├── models.py       # Pydantic Schemas
│   └── publisher_sender.py # Skrip Pengirim untuk Docker Compose (Bonus)
├── tests/
│   └── test_aggregator.py # 6 Unit Tests (pytest)
├── dedup_store.db      # Database Deduplikasi (Diabaikan oleh .gitignore)
├── docker-compose.yml  # Definisi Layanan Publisher & Aggregator (Bonus)
├── Dockerfile          # Instruksi Build Image
└── requirements.txt
```

-----

## Cara Menjalankan Layanan

### Persyaratan

  * **Python 3.11+** terinstal (untuk *unit testing* lokal dan *venv*).
  * Docker Desktop (Windows/Linux) terinstal dan berjalan.
  * Terminal Windows (PowerShell/CMD).

-----

## I. Persiapan Virtual Environment

Anda harus mengaktifkan *virtual environment* sebelum melakukan *build* atau *testing* di *host*.

1.  **Buat Virtual Environment:**

    ```powershell
    python -m venv venv
    ```

2.  **Aktifkan Environment:**

    ```powershell
    .\venv\Scripts\activate
    ```

3.  **Instal Dependensi (Termasuk Pytest):**

    ```powershell
    pip install -r requirements.txt
    ```

-----

## II. Eksekusi Layanan Docker

### A. Opsi Wajib: Single Container (Aggregator Saja)

Ini menjalankan Aggregator dan mengasumsikan *Publisher* adalah Postman/cURL dari *host*.

1.  **Build Image:** (Pastikan `venv` aktif)

    ```powershell
    docker build -t uts-aggregator .
    ```

2.  **Run Container:**

    ```powershell
    docker run -d --name aggregator-service -p 8080:8080 uts-aggregator
    ```

    (Layanan dapat diakses di `http://localhost:8080`).

### B. Opsi Bonus (+10%): Docker Compose (Aggregator & Publisher)

Ini menjalankan **dua *service* terpisah** dan mensimulasikan lalu lintas log otomatis.

1.  **Run Services:**

    ```powershell
    docker-compose up --build -d
    ```

      * Container `log_aggregator` akan diekspos di `http://localhost:8080`.
      * Container `log_publisher` akan otomatis mengirim event ke jaringan internal dan keluar.

2.  **Monitor Log (Opsional):**

    ```powershell
    docker logs log_aggregator -f
    ```

-----

## III. Menjalankan Unit Tests (Opsional di Host)

Unit tests harus dijalankan setelah mengaktifkan *venv* dan sebelum *build* Docker.

  * **Set PYTHONPATH (Wajib di Windows):**
    ```powershell
    $env:PYTHONPATH="."
    ```
  * **Jalankan Pytest:**
    ```powershell
    pytest tests/test_aggregator.py
    ```
-----

## Endpoint API Log Aggregator

Base URL: `http://localhost:8080`

| Metode | Path | Deskripsi | Contoh JSON Request/Response |
| :--- | :--- | :--- | :--- |
| `POST` | `/publish` | Menerima event dari publisher dan memasukkannya ke antrean pemrosesan. | **Request Body (JSON Event):**<br>`json{  "topic": "auth.login",  "event_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",  "timestamp": "2025-10-21T10:00:00.123456Z",  "source": "web-frontend",  "payload": { "content": "User 101 logged in." }}`<br>**Response (202 Accepted):**<br>`json{"status": "accepted", "event_id": "..."}`|
| `GET` | `/events` | Mengembalikan daftar event unik yang **telah berhasil diproses** (dari Deduplication Store). | **Response Body:**<br>`json[  {    "event_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",    "topic": "auth.login",    "timestamp": "2025-10-21T10:00:00.123456"  }]`|
| `GET` | `/stats` | Mengembalikan metrik operasional sistem Aggregator. | **Response Body:**<br>`json{  "received": 50,  "unique_processed": 30,  "duplicate_dropped": 20,  "topics": ["auth.login", "order.create"],  "uptime": 1250}`|

## Unit Tests (Pytest)

Layanan Aggregator dijamin berfungsi dengan benar dan stabil melalui 6 *unit tests* berbasis `pytest` dan `pytest-asyncio`. Pengujian berfokus pada validasi *state* sistem, *idempotency*, dan *toleransi kegagalan*.

| Test ID | Fungsi yang Diuji | Deskripsi Singkat | Cakupan Rubrik |
| :--- | :--- | :--- | :--- |
| **Test 1** | `test_t1_deduplication_validity` | Memverifikasi **Idempotency** dengan mengirimkan dua *event* yang identik (`event\_id` sama). Memastikan **`unique_processed`** adalah 1 dan **`duplicate_dropped`** adalah 1. | Dedup/Idempotency, API, Stats |
| **Test 2** | `test_t2_persistence_after_restart` | Menguji **Toleransi Kegagalan** dan **Persistensi Dedup Store**. Mensimulasikan *restart* (*instance* Aggregator baru) setelah event diproses, lalu mengirimkan duplikat event lama. Memastikan *instance* baru menolak event tersebut. | Idempotency, Toleransi Kegagalan |
| **Test 3** | `test_t3_event_schema_validation` | Memastikan validasi skema **Pydantic** pada *endpoint* `/publish` bekerja dengan benar, khususnya menolak *event* yang tidak memiliki `event_id` (kunci unik). | Validasi Skema |
| **Test 4** | `test_t4_get_stats_consistency` | Menguji **Konsistensi Statistik** dan *state cleanup* antar *test*. Memastikan `received`, `unique_processed`, `duplicate_dropped`, dan `topics` akurat setelah pengiriman dua *event* unik. | API, Stats |
| **Test 5** | `test_t5_get_events_with_topic_filter` | Menguji fungsi *filtering* pada *endpoint* `/events?topic=...`. Memastikan deduplikasi dan filter *topic* bekerja secara simultan, hanya mengembalikan event unik yang sesuai dengan filter. | API, Dedup |
| **Test 6** | `test_t6_stress_small_batch` | Menguji *baseline* **Performa** dan *state* sistem saat memproses $100$ *event* secara berturut-turut. Memastikan waktu eksekusi berada di bawah batas wajar ($< 5$ detik). | Performa |

-----

## Video Demo

[Cantumkan Link Video Demo YouTube Anda di sini]
(Video mendemonstrasikan Build, Run, Pengiriman Duplikat, dan Persistensi State/Restart).