"""
Telegram Bot Interface cho hệ thống chấm công DetectFakeIMG.

Bot này nhận file ảnh (Document) từ người dùng, gọi trực tiếp vào
Analysis Orchestrator đã xây dựng, và trả về kết quả cho người dùng.
"""
import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile

import os
from dotenv import load_dotenv

# Tải file .env trước khi import bất kỳ cái gì khác
load_dotenv()

from app.services import analysis_orchestrator
from app.core.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Đảm bảo thư mục lưu tạm tồn tại
TEMP_DIR = settings.TEMP_DIR
TEMP_DIR.mkdir(parents=True, exist_ok=True)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
    raise ValueError("Chưa cấu hình TELEGRAM_TOKEN trong file .env!")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Đảm bảo thư mục lưu tạm tồn tại
TEMP_DIR = settings.TEMP_DIR
TEMP_DIR.mkdir(parents=True, exist_ok=True)


@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    """Xử lý lệnh /start."""
    welcome_text = (
        "🏗️ **Hệ Thống Chấm Công Chống Giả Mạo**\n\n"
        "Xin chào! Vui lòng gửi ảnh chụp công trường để chấm công.\n\n"
        "⚠️ **QUAN TRỌNG:**\n"
        "Để hệ thống đọc được thời gian thực tế, bạn **BẮT BUỘC** phải gửi ảnh dưới dạng **FILE (Document)**, "
        "không gửi dưới dạng Ảnh (Photo) bình thường vì Telegram sẽ xóa mất dữ liệu thời gian."
    )
    await message.reply(welcome_text, parse_mode="Markdown")


@dp.message(F.photo)
async def handle_photo(message: types.Message):
    """Cảnh báo khi người dùng gửi dạng Ảnh thường (bị mất EXIF)."""
    warning = (
        "❌ Bạn đang gửi dưới dạng **Ảnh** nén của Telegram.\n"
        "Điều này làm mất dữ liệu thời gian gốc (EXIF).\n\n"
        "👉 Vui lòng nhấn vào biểu tượng 📎 (Đính kèm) -> Chọn **File** -> Chọn ảnh từ thư viện."
    )
    await message.reply(warning, parse_mode="Markdown")


@dp.message(F.document)
async def handle_document(message: types.Message):
    """Xử lý khi người dùng gửi ảnh dưới dạng File (giữ nguyên EXIF)."""
    document = message.document
    
    # Chỉ nhận file ảnh
    if document.mime_type not in ["image/jpeg", "image/png", "image/heic"]:
        await message.reply("❌ Chỉ chấp nhận file định dạng JPG hoặc PNG.")
        return

    msg = await message.reply("⏳ Đang tải ảnh và phân tích... Vui lòng đợi.")
    
    file_id = document.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    
    # Tải file về thư mục tạm
    download_path = TEMP_DIR / f"{file_id}_{document.file_name}"
    await bot.download_file(file_path, destination=download_path)
    
    try:
        # Gọi trực tiếp vào Orchestrator mà chúng ta đã viết cho Backend!
        result = analysis_orchestrator.run_full_analysis(
            image_path=download_path, 
            filename=document.file_name
        )
        
        # Format kết quả trả về
        if result.verdict == "AUTHENTIC":
            verdict_icon = "✅"
            verdict_title = "ẢNH HỢP LỆ"
        elif result.verdict == "SUSPICIOUS":
            verdict_icon = "⚠️"
            verdict_title = "ĐÁNG NGỜ"
        else:
            verdict_icon = "❌"
            verdict_title = "ẢNH GIẢ MẠO / FAKE / AI"
            
        # Lấy GPS nếu có
        gps_info = "Không có dữ liệu vị trí"
        if result.exif_analysis.gps:
            lat = result.exif_analysis.gps.latitude
            lon = result.exif_analysis.gps.longitude
            gps_info = f"[Xem trên Google Maps](https://www.google.com/maps?q={lat},{lon})"
            
        reply_text = (
            f"{verdict_icon} **KẾT QUẢ KIỂM TRA: {verdict_title}**\n\n"
            f"Tên file: `{result.filename}`\n"
            f"Điểm tin cậy: **{result.overall_score}/100**\n"
            f"Đánh giá: **{result.verdict_description}**\n\n"
            f"🕒 Thời gian chụp: {result.timestamp_verification.exif_timestamp or 'Không tìm thấy'}\n"
            f"📍 Địa điểm: {gps_info}\n"
            f"🤖 Tỉ lệ do AI tạo: {result.ai_detection.ai_probability:.0%}\n\n"
            f"**Chi tiết phát hiện:**\n"
        )
        
        # Lọc cảnh báo
        flags_to_show = [f for f in result.all_flags if "🔴" in f or "⚠️" in f or "❌" in f]
        if flags_to_show:
            for flag in flags_to_show[:7]:
                reply_text += f"- {flag}\n"
        else:
            reply_text += "- ✅ Tất cả thông số đều bình thường.\n"
            
        await msg.edit_text(reply_text, parse_mode="Markdown", disable_web_page_preview=True)
        
        # Gửi ảnh Heatmap nếu phát hiện cắt ghép
        if result.ela_analysis.edited_regions_detected and result.ela_analysis.heatmap_base64:
            import base64
            heatmap_bytes = base64.b64decode(result.ela_analysis.heatmap_base64)
            photo = BufferedInputFile(heatmap_bytes, filename="heatmap.png")
            
            heatmap_caption = (
                "🔍 **BẢN ĐỒ TẦM NHIỆT (PHÁT HIỆN CẮT GHÉP)**\n"
                "👉 Những vùng có **màu Đỏ, Cam, Vàng** rực sáng lên trên ảnh là những điểm bị chỉnh sửa, chèn chữ, hoặc ghép thêm vật thể (như sửa lại giờ/ngày)."
            )
            await message.reply_photo(photo=photo, caption=heatmap_caption, parse_mode="Markdown")
            
    except Exception as e:
        logger.exception("Lỗi khi xử lý bot")
        await msg.edit_text(f"❌ Có lỗi xảy ra trong quá trình phân tích: {e}")
    finally:
        # Xóa file tạm
        if download_path.exists():
            download_path.unlink()


async def main():
    logger.info("Khởi động Bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
