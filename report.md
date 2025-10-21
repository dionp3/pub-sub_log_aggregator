# Laporan Pub-Sub Log Aggregator dengan Idempotent Consumer dan Deduplication

**Nama Proyek:** pub-sub\_log\_aggregator

## 1\. Bagian Teori (Keterkaitan Bab 1–7)

### T1 (Bab 1): Karakteristik Sistem Terdistribusi dan Trade-off

Sistem terdistribusi dicirikan oleh **concurrency** (eksekusi komponen secara bersamaan), **lack of a global clock** (waktu lokal yang berbeda-beda), dan **independent failure modes** (komponen gagal sendiri-sendiri) (Tanenbaum & Van Steen, 2018, hlm. 2). Pada desain Pub-Sub log aggregator, *trade-off* utama adalah antara **Latency** dan **Consistency**. Agregat log mengutamakan **ketersediaan** (*availability*) dan *throughput* tinggi, sehingga sering mengorbankan konsistensi yang ketat untuk mencapai *eventual consistency*. Keputusan ini memungkinkan sistem mentoleransi *network partition* dan *at-least-once delivery* dengan overhead yang minimal.

### T2 (Bab 2): Perbandingan Arsitektur Client-Server vs. Publish-Subscribe

Arsitektur **Client-Server** melibatkan komunikasi *tightly coupled* di mana klien secara langsung meminta layanan dari server. Sebaliknya, **Publish-Subscribe (Pub-Sub)** adalah arsitektur *decoupled* yang memungkinkan pemisahan spasial (publisher dan subscriber tidak saling kenal), temporal (tidak perlu aktif bersamaan), dan sinkronisasi (komunikasi asinkron) (Tanenbaum & Van Steen, 2018, hlm. 43). Memilih Pub-Sub untuk log aggregator sangat tepat karena:

1.  **Skalabilitas**: Mudah menambahkan sumber log (publisher) baru tanpa memengaruhi consumer.
2.  **Reliabilitas**: Jika consumer gagal, event tetap berada di *message buffer* (atau *queue*) hingga consumer pulih.
3.  **Throughput**: Komunikasi asinkron memungkinkan *producer* bekerja cepat tanpa menunggu pemrosesan *consumer*.

### T3 (Bab 3): At-least-once vs. Exactly-once Delivery

  * **At-least-once delivery** menjamin event dikirimkan setidaknya satu kali, yang berarti event yang sama mungkin diterima berulang kali (duplikasi).
  * **Exactly-once delivery** menjamin event diterima tepat satu kali, yang secara praktis sangat sulit dicapai dan memerlukan *two-phase commit* atau protokol kompleks lainnya.

**Idempotent consumer** sangat krusial dalam keberadaan *retries* (pengiriman ulang) karena sistem Pub-Sub sering kali hanya menjamin *at-least-once delivery* (Tanenbaum & Van Steen, 2018, hlm. 162). Ketika *publisher* mengirim ulang event yang sama akibat kegagalan *acknowledgement*, *consumer* yang idempotent dapat mendeteksi duplikat tersebut berdasarkan **`event_id`** dan hanya mengeksekusi logika pemrosesan yang mengubah *state* satu kali, mencegah inkonsistensi data.

### T4 (Bab 4): Skema Penamaan untuk Topic dan Event ID

  * **Topic**: Skema penamaan harus hierarkis untuk memudahkan *filtering* dan *subscription*. Contoh: **`aplikasi.subsystem.level`** (misalnya, `web.auth.error` atau `api.order.info`).
  * **Event ID (`event_id`)**: Harus menggunakan format yang menjamin keunikan global, seperti **UUID (Universally Unique Identifier)**, yang *collision-resistant* secara probabilistik.

Dampak pada **Deduplication (Dedup)** adalah mutlak: Dedup store menggunakan tuple **(`event_id`)** sebagai kunci primer (Primary Key) yang unik untuk menentukan apakah event tersebut sudah pernah diproses atau belum. Penamaan yang unik menjamin akurasi mekanisme **idempotency**.

### T5 (Bab 5): Ordering dan Batasannya

Pada konteks log aggregator, **Total Ordering** (urutan global yang absolut) **tidak diperlukan**. Log dari berbagai sumber yang berbeda sering kali tidak memiliki hubungan kausal (misalnya, *log A* dari Server X tidak terkait dengan *log B* dari Server Y). Kebutuhan utamanya adalah **Partial Ordering** atau **Causal Ordering**—mempertahankan urutan event dari satu sumber yang sama (Tanenbaum & Van Steen, 2018, hlm. 248).

**Pendekatan Praktis**: Menggunakan *event timestamp* (ISO8601) yang dicatat saat event dibuat. Batasannya adalah **Clock Skew** (perbedaan waktu antar mesin). Jika dua event hampir bersamaan dibuat di mesin yang berbeda, *global ordering* berdasarkan timestamp dapat terbalik. Untuk agregator, *partial ordering* yang disediakan oleh *in-memory queue* dan *event timestamp* yang bersifat metadata sudah memadai.

### T6 (Bab 6): Failure Modes dan Strategi Mitigasi

  * **Failure Modes**:
    1.  **Duplikasi Event** (*Duplicate delivery*): Paling umum akibat *retry* pada *at-least-once* (Tanenbaum & Van Steen, 2018, hlm. 336).
    2.  **Out-of-Order delivery**: Event tiba tidak sesuai urutan pengiriman.
    3.  **Crash**: Consumer/Aggregator mati tiba-tiba.
  * **Strategi Mitigasi**:
      * **Retry dan Backoff**: Publisher harus menggunakan *retry* dengan **exponential backoff** untuk memastikan event yang gagal terkirim tanpa membebani sistem.
      * **Durable Dedup Store (SQLite)**: Menyimpan *event state* yang sudah diproses pada media persisten (disk). Ini adalah kunci untuk mencapai **Toleransi Kegagalan**; jika Aggregator *crash* dan di-restart, *store* dimuat ulang dan mencegah pemrosesan event lama.

### T7 (Bab 7): Eventual Consistency dan Peran Idempotency + Dedup

**Eventual Consistency** adalah model konsistensi yang paling longgar, di mana jika tidak ada pembaruan lebih lanjut, semua replika data akan konvergen pada nilai yang sama (Tanenbaum & Van Steen, 2018, hlm. 433). Ini adalah target konsistensi yang realistis untuk log aggregator.

**Peran Idempotency dan Dedup**:
Dalam sistem *at-least-once*, duplikasi adalah sumber utama inkonsistensi. **Idempotency** (logika "lakukan operasi hanya sekali") yang didukung oleh **Deduplication Store** (mencatat event ID yang sudah diproses) memastikan bahwa **duplikat event** tidak mengubah *state* hasil pemrosesan. Dengan menolak duplikat yang berlebihan, sistem menjamin bahwa log unik yang disimpan akan seragam di antara *state* yang berbeda, sehingga mencapai **Eventual Consistency**.

### T8 (Bab 1–7): Metrik Evaluasi Sistem

Metrik evaluasi harus secara langsung mencerminkan kualitas layanan:

  * **Throughput**: Jumlah event yang diterima dan diproses per detik. Desain menggunakan **asyncio** (Bab 3) meningkatkan *throughput* karena memungkinkan *consumer* dan *API endpoint* bekerja secara non-blocking.
  * **Latency**: Waktu yang dibutuhkan dari `POST /publish` hingga event selesai diproses. Latency rendah dicapai karena *API endpoint* segera mengembalikan respons (status 202) setelah memasukkan event ke `asyncio.Queue` (Bab 3), meminimalkan waktu tunggu.
  * **Duplicate Rate**: Persentase event yang dideteksi dan diabaikan sebagai duplikat. Metrik ini secara langsung mengukur efektivitas *dedup store* dan seberapa sering *at-least-once delivery* terjadi.

-----

## 2\. Bagian Implementasi dan Desain

### 2.1 Arsitektur Sistem

Layanan Aggregator menggunakan arsitektur *monolithic* di dalam satu *container*, dengan pemisahan *concern* asinkron:

1.  **API Frontend (FastAPI)**: Menerima *request* `POST /publish`.
2.  **Internal Queue (`asyncio.Queue`)**: Bertindak sebagai *buffer* pesan (broker internal).
3.  **Consumer Task**: Tugas latar belakang asinkron yang menarik event dari *queue*.
4.  **Deduplication Store (SQLite)**: Database lokal, persisten, dan *file-based* untuk mencatat `event_id` yang telah diproses.

### 2.2 Keputusan Desain Utama

| Area | Keputusan Desain | Keterkaitan dengan Bab |
| :--- | :--- | :--- |
| **Idempotency & Dedup** | Menggunakan **SQLite3** dan **`event_id`** sebagai `PRIMARY KEY`. Consumer menggunakan **`SELECT`** untuk cek keberadaan dan **`INSERT OR IGNORE`** untuk penulisan. | Bab 7 (Konsistensi), Bab 6 (Toleransi Kegagalan) |
| **Persistensi** | File `dedup_store.db` dijamin persisten di dalam *container* dan tahan terhadap *restart*. | Bab 6 (Toleransi Kegagalan) |
| **Delivery** | Menerima *at-least-once delivery* dari publisher. Duplikasi dicatat di *stats* dan dibuang di consumer. | Bab 3 (Semantik Pengiriman) |
| **Concurrency** | Menggunakan **`asyncio`** untuk *non-blocking I/O* pada API dan **Consumer Task** agar *throughput* tinggi. | Bab 1 (Concurrency), Bab 3 (Komunikasi) |

### 2.3 Perintah Run Singkat

Instruksi ini mengasumsikan file kode berada di folder `pub-sub_log_aggregator`.

1.  **Build Image:**
    ```bash
    docker build -t uts-aggregator .
    ```
2.  **Run Container:**
    ```bash
    docker run -d --name aggregator-service -p 8080:8080 uts-aggregator
    ```
3.  **Stop Container:**
    ```bash
    docker stop aggregator-service
    ```

### 2.4 Metrik dan Pengujian

Endpoint **`GET /stats`** menyediakan metrik *real-time* yang vital:

  * `received`: Total event yang masuk (mengukur beban kerja).
  * `unique_processed`: Event yang berhasil diproses (mengukur *throughput* bersih).
  * `duplicate_dropped`: Event yang terdeteksi dan diabaikan (mengukur *duplicate rate*).

**Unit Tests (Pytest)** memverifikasi fungsionalitas inti:

1.  Validasi Deduplikasi (*idempotency*).
2.  Uji Persistensi Dedup Store (*simulasi restart*).
3.  Uji Konsistensi `GET /stats`.
4.  Validasi Skema Event.
5.  Uji *Stress* Batch Kecil.

-----

## Referensi

Tanenbaum, A. S., & Van Steen, M. (2018). *Distributed systems: principles and paradigms*. Pearson Education Limited.