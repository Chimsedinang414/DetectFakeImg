import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from datetime import datetime

import customtkinter as ctk
import openpyxl

from app.services import analysis_orchestrator
from app.core.config import settings

# Cấu hình giao diện hiện đại (Web-like)
ctk.set_appearance_mode("Dark")  # Giao diện tối
ctk.set_default_color_theme("blue")  # Màu chủ đạo xanh dương

class DetectFakeIMG_ModernApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("DetectFakeIMG - Trạm Quét Chống Gian Lận (Phiên Bản AI)")
        self.geometry("850x650")
        self.resizable(False, False)

        # Biến lưu trữ
        self.selected_files = [] # Danh sách các file được chọn
        self.output_folder = ctk.StringVar()
        self.is_scanning = False

        self._build_ui()

    def _build_ui(self):
        # Header
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        self.title_lbl = ctk.CTkLabel(self.header_frame, text="HỆ THỐNG QUÉT ẢNH OFFLINE", font=ctk.CTkFont(family="Inter", size=24, weight="bold"))
        self.title_lbl.pack()
        
        self.sub_lbl = ctk.CTkLabel(self.header_frame, text="Tự động phát hiện chỉnh sửa, cắt ghép, và AI tạo ra.", font=ctk.CTkFont(size=14), text_color="gray")
        self.sub_lbl.pack()

        # Khung 1: Chọn Ảnh Đầu Vào
        self.frame_in = ctk.CTkFrame(self)
        self.frame_in.pack(fill="x", padx=20, pady=10)
        
        self.lbl_in = ctk.CTkLabel(self.frame_in, text="1. Nguồn Ảnh Đầu Vào", font=ctk.CTkFont(weight="bold"))
        self.lbl_in.pack(anchor="w", padx=15, pady=(10, 0))

        self.btn_frame = ctk.CTkFrame(self.frame_in, fg_color="transparent")
        self.btn_frame.pack(fill="x", padx=15, pady=10)

        self.btn_files = ctk.CTkButton(self.btn_frame, text="📄 Chọn Từng Ảnh", command=self.browse_files, fg_color="#3498db", hover_color="#2980b9")
        self.btn_files.pack(side="left", padx=(0, 10))

        self.btn_folder = ctk.CTkButton(self.btn_frame, text="📁 Chọn Cả Thư Mục", command=self.browse_folder, fg_color="#8e44ad", hover_color="#732d91")
        self.btn_folder.pack(side="left")
        
        self.lbl_selected = ctk.CTkLabel(self.frame_in, text="Chưa chọn ảnh nào.", text_color="gray")
        self.lbl_selected.pack(anchor="w", padx=15, pady=(0, 10))

        # Khung 2: Chọn Nơi Lưu Báo Cáo
        self.frame_out = ctk.CTkFrame(self)
        self.frame_out.pack(fill="x", padx=20, pady=10)

        self.lbl_out = ctk.CTkLabel(self.frame_out, text="2. Lưu Báo Cáo Excel Tại", font=ctk.CTkFont(weight="bold"))
        self.lbl_out.pack(anchor="w", padx=15, pady=(10, 0))

        self.out_inner = ctk.CTkFrame(self.frame_out, fg_color="transparent")
        self.out_inner.pack(fill="x", padx=15, pady=10)

        self.entry_out = ctk.CTkEntry(self.out_inner, textvariable=self.output_folder, state="readonly", width=550)
        self.entry_out.pack(side="left", padx=(0, 10))
        
        self.btn_out = ctk.CTkButton(self.out_inner, text="Chọn Nơi Lưu", command=self.browse_output)
        self.btn_out.pack(side="left")

        # Nút Quét Lớn
        self.start_btn = ctk.CTkButton(self, text="🚀 BẮT ĐẦU QUÉT HÀNG LOẠT", font=ctk.CTkFont(size=16, weight="bold"), fg_color="#27ae60", hover_color="#219653", height=50, command=self.start_scan_thread)
        self.start_btn.pack(fill="x", padx=20, pady=(20, 10))

        # Thanh tiến trình
        self.progress_bar = ctk.CTkProgressBar(self, height=10)
        self.progress_bar.pack(fill="x", padx=20, pady=5)
        self.progress_bar.set(0)

        self.status_lbl = ctk.CTkLabel(self, text="Sẵn sàng.", font=ctk.CTkFont(size=12), text_color="gray")
        self.status_lbl.pack(anchor="w", padx=20)

        # Log Textbox (Thay cho Listbox cũ cho đẹp)
        self.log_box = ctk.CTkTextbox(self, height=120, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_box.pack(fill="both", padx=20, pady=(10, 20))
        self.log_box.configure(state="disabled")

    def log(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert(tk.END, message + "\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state="disabled")
        self.update_idletasks()

    def browse_files(self):
        files = filedialog.askopenfilenames(
            title="Chọn các file ảnh",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.heic")]
        )
        if files:
            self.selected_files = [Path(f) for f in files]
            self.lbl_selected.configure(text=f"Đã chọn {len(self.selected_files)} file lẻ.")

    def browse_folder(self):
        folder = filedialog.askdirectory(title="Chọn thư mục chứa ảnh")
        if folder:
            self.selected_files = []
            for ext in settings.ALLOWED_EXTENSIONS + ['.heic', '.HEIC']:
                self.selected_files.extend(list(Path(folder).rglob(f"*{ext}")))
                self.selected_files.extend(list(Path(folder).rglob(f"*{ext.upper()}")))
            
            # Xóa trùng lặp nếu có do rglob
            self.selected_files = list(set(self.selected_files))
            self.lbl_selected.configure(text=f"Đã nạp {len(self.selected_files)} ảnh từ thư mục.")

    def browse_output(self):
        folder = filedialog.askdirectory(title="Chọn nơi lưu file báo cáo Excel")
        if folder:
            self.output_folder.set(folder)

    def start_scan_thread(self):
        out_dir = self.output_folder.get()

        if not self.selected_files:
            messagebox.showwarning("Chưa có ảnh", "Vui lòng chọn ảnh hoặc thư mục cần quét!")
            return
        if not out_dir:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng chọn thư mục để xuất báo cáo Excel!")
            return

        if self.is_scanning:
            return

        self.is_scanning = True
        self.start_btn.configure(state="disabled", text="⏳ HỆ THỐNG ĐANG PHÂN TÍCH...", fg_color="#f39c12", hover_color="#d68910")
        self.progress_bar.set(0)
        
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.configure(state="disabled")

        threading.Thread(target=self.run_scan, args=(self.selected_files, out_dir), daemon=True).start()

    def run_scan(self, image_files, out_dir):
        try:
            total_files = len(image_files)
            if total_files == 0:
                self.log("⚠️ Lỗi: Không có file ảnh nào hợp lệ!")
                self.reset_ui()
                return

            self.log(f"🚀 Bắt đầu quét {total_files} bức ảnh...")

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Báo Cáo Điểm Danh"
            headers = ["Tên File", "Trạng Thái", "Điểm Tin Cậy", "Thời Gian Gốc", "Tỉ lệ AI", "GPS", "Cảnh Báo"]
            ws.append(headers)

            for idx, img_path in enumerate(image_files):
                self.status_lbl.configure(text=f"Đang phân tích: {img_path.name} ({idx+1}/{total_files})")
                self.log(f"[{idx+1}/{total_files}] Soi lỗi ảnh: {img_path.name}")
                
                try:
                    result = analysis_orchestrator.run_full_analysis(img_path, img_path.name)
                    
                    gps = ""
                    if result.exif_analysis.gps:
                        gps = f"{result.exif_analysis.gps.latitude}, {result.exif_analysis.gps.longitude}"

                    warnings = " | ".join([f for f in result.all_flags if "🔴" in f or "⚠️" in f])
                    
                    row = [
                        result.filename,
                        result.verdict_description,
                        result.overall_score,
                        result.timestamp_verification.exif_timestamp or "Không có",
                        f"{result.ai_detection.ai_probability:.0%}",
                        gps,
                        warnings
                    ]
                    ws.append(row)

                except Exception as e:
                    self.log(f"  ❌ Lỗi file: {e}")
                    ws.append([img_path.name, "LỖI PHÂN TÍCH", "", "", "", "", str(e)])

                # Cập nhật thanh tiến trình
                self.progress_bar.set((idx + 1) / total_files)

            # Lưu file Excel
            report_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            excel_path = Path(out_dir) / f"BaoCao_DiemDanh_{report_time}.xlsx"
            wb.save(excel_path)

            self.log(f"==============================")
            self.log(f"✅ HOÀN TẤT! Đã quét xong {total_files} ảnh.")
            self.log(f"📁 Báo cáo đã lưu tại: {excel_path}")
            messagebox.showinfo("Thành Công", f"Phân tích hoàn tất!\nĐã xuất {total_files} kết quả ra Excel.")

        except Exception as e:
            self.log(f"❌ Lỗi hệ thống: {e}")
            messagebox.showerror("Lỗi Nghiêm Trọng", f"Đã xảy ra lỗi: {e}")
        finally:
            self.reset_ui()

    def reset_ui(self):
        self.is_scanning = False
        self.start_btn.configure(state="normal", text="🚀 BẮT ĐẦU QUÉT HÀNG LOẠT", fg_color="#27ae60", hover_color="#219653")
        self.status_lbl.configure(text="Sẵn sàng.")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    app = DetectFakeIMG_ModernApp()
    app.mainloop()
