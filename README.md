# FluentDict

Từ điển Anh–Việt offline, sử dụng dữ liệu từ app [TFlat Dictionary](https://play.google.com/store/apps/details?id=com.vn.dic.e.v.ui) với hơn 103,000 từ.

## Tính năng

- Tra nghĩa từ với phiên âm, ví dụ minh hoạ và cụm từ
- Gợi ý từ khi gõ (autocomplete)
- Nhận dạng dạng biến thể (inflections) và tra từ gốc
- Từ ngẫu nhiên
- Lịch sử tra từ (lưu local)

## Cấu trúc

| File | Mô tả |
|------|-------|
| `index.html` | Giao diện web, standalone — mở thẳng trên browser |
| `style.css` | Stylesheet |
| `main.py` | FastAPI server (Python, cũ — giữ lại để reference) |
| `parse.py` | Parser cho TFlat DB format |

## API Backend

Dự án sử dụng [Fluentez Backend](https://github.com/Fluentez/FluentDict) (Express.js/Node.js) làm API server.

Các endpoint:

```
GET /api/v1/dict/search?q=hello&limit=8
GET /api/v1/dict/word/:word
GET /api/v1/dict/random
```

## Lấy database TFlat

1. Lấy APK của TFlat Dict (từ điện thoại hoặc [APKPure](https://apkpure.com/dich-tieng-anh-tflat-translate/com.vn.dic.e.v.ui))
2. Đổi đuôi `.apk` → `.zip` rồi giải nén
3. Đổi `assets/o_v3` → `o_v3.zip` rồi giải nén
4. Lấy file `av_v3.db` — set đường dẫn vào env `DICT_DB_PATH`
