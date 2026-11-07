"""Reservation UI and sequential subprocess execution for PoseGui."""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from reservation_queue import ReservationQueue, set_output, write_json

STATE_LABELS = {'pending': '待機中', 'running': '解析中', 'done': '完了',
                'failed': '失敗'}


class ReservationMixin:
    def _init_reservations(self, base_dir, output_names):
        self._reservation_base = Path(base_dir)
        self._output_names = output_names
        try:
            self.reservations = ReservationQueue(self._reservation_base / 'analysis_queue.json',
                Path(self.values['OUTPUT_DIRECTORY']).expanduser().parent)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror('予約ファイルを読み込めません', f'{exc}\n予約ファイルを上書きせず終了します。', parent=self)
            self.destroy()
            raise
        self.queue_active = False
        self.current_job_id = None
        self._queue_stop = threading.Event()
        self._close_after_stop = False
        self._preview_started = set()
        self._preview_photos = {}
        self._preview_info = {}
        self._job_tail = []
        self._poll_token = None
        self._next_token = None
        self.protocol('WM_DELETE_WINDOW', self._queue_close)

    def _build_reservations(self, parent):
        header = ttk.Frame(parent, padding=(8, 8))
        header.pack(fill='x')
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text='予約一覧', font=('Yu Gothic UI', 13, 'bold')).grid(row=0, column=0, sticky='w')
        run_actions = ttk.Frame(header)
        run_actions.grid(row=0, column=1, sticky='e')
        ttk.Style(self).configure('AnalysisStart.TButton', font=('Yu Gothic UI', 11, 'bold'), padding=(18, 10))
        self.cancel_button = ttk.Button(run_actions, text='予約実行を中断', command=self._cancel, state='disabled')
        self.cancel_button.pack(side='left', padx=(0, 8))
        self.start_button = ttk.Button(run_actions, text='▶ 解析を開始', style='AnalysisStart.TButton', command=self._start)
        self.start_button.pack(side='left')
        root_bar = ttk.Frame(parent, padding=(8, 10))
        root_bar.pack(fill='x')
        ttk.Label(root_bar, text='予約の出力先（動画ごとにフォルダーを作成）').pack(anchor='w')
        root_line = ttk.Frame(root_bar)
        root_line.pack(fill='x', pady=(4, 0))
        self.queue_output_root = tk.StringVar(value=self.reservations.output_root)
        ttk.Entry(root_line, textvariable=self.queue_output_root).pack(side='left', fill='x', expand=True)
        ttk.Button(root_line, text='参照…', command=self._choose_queue_root).pack(side='right', padx=(6, 0))
        tools = ttk.Frame(parent, padding=(8, 0, 8, 8))
        tools.pack(fill='x')
        for text, command in [
                ('動画を追加…', self._add_videos), ('現在の入力を追加', self._add_current_video),
                ('削除', self._remove_reservations), ('上へ', lambda: self._move_reservation(-1)),
                ('下へ', lambda: self._move_reservation(1)), ('再予約', self._retry_reservations),
                ('設定を確認', self._show_reservation_settings)]:
            ttk.Button(tools, text=text, command=command).pack(side='left', padx=(0, 5))
        hint = ttk.Label(parent, text='追加時の「解析設定」を予約ごとに保存します。待機中の予約を登録順に1本ずつ実行します。',
                         padding=(8, 0, 8, 6))
        hint.pack(anchor='w')
        tree_frame = ttk.Frame(parent, padding=(8, 0))
        tree_frame.pack(fill='both', expand=True)
        ttk.Style(self).configure('Reservation.Treeview', rowheight=76)
        self.reservation_tree = ttk.Treeview(tree_frame, style='Reservation.Treeview',
            columns=('order', 'state', 'output'), selectmode='extended')
        self.reservation_tree.heading('#0', text='プレビュー / 動画名')
        self.reservation_tree.column('#0', width=370, minwidth=240)
        for name, title, width in [('order', '順番', 55), ('state', '状態', 90), ('output', '出力フォルダー', 260)]:
            self.reservation_tree.heading(name, text=title)
            self.reservation_tree.column(name, width=width, minwidth=width if name != 'output' else 100,
                                         stretch=name == 'output', anchor='w')
        scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=self.reservation_tree.yview)
        self.reservation_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.reservation_tree.pack(side='left', fill='both', expand=True)
        self.reservation_tree.bind('<<TreeviewSelect>>', lambda e: self._reservation_details())
        self.queue_summary = tk.StringVar()
        ttk.Label(parent, textvariable=self.queue_summary, padding=(8, 5)).pack(anchor='w')
        self.queue_details = tk.StringVar(value='動画を追加してください。サムネイルは動画から自動で作成します。')
        details = ttk.Label(parent, textvariable=self.queue_details, wraplength=1000, padding=(8, 0, 8, 8))
        details.pack(fill='x')
        parent.bind('<Configure>', lambda event: (details.configure(wraplength=max(300, event.width - 20)),
                                                 hint.configure(wraplength=max(300, event.width - 20))))
        self._placeholder = tk.PhotoImage(master=self, width=104, height=58)
        self._placeholder.put('#d5dce5', to=(0, 0, 104, 58))
        self._refresh_reservations()
        self._start_previews(self.reservations.jobs)

    def _choose_queue_root(self):
        path = filedialog.askdirectory(title='予約の出力先', initialdir=self.queue_output_root.get() or str(Path.home()))
        if path:
            self.queue_output_root.set(path)
            self.reservations.output_root = path
            self._save_reservations()

    def _save_reservations(self):
        try:
            self.reservations.save()
            return True
        except OSError as exc:
            self._queue_stop.set()
            if self.process is not None and self.process.poll() is None:
                try:
                    self.process.terminate()
                except OSError:
                    pass
            messagebox.showerror('予約を保存できません', str(exc), parent=self)
            return False

    def _add_videos(self):
        videos = filedialog.askopenfilenames(title='解析する動画を登録順に選択',
            filetypes=[('動画ファイル', '*.mp4 *.MP4 *.mov *.MOV *.avi *.mkv'), ('すべて', '*.*')])
        if videos:
            self._register_videos(videos)

    def _add_current_video(self):
        video = self.vars['INPUT_VIDEO_FILE'].get().strip()
        if video:
            self._register_videos([video], use_thumbnail=True)
        else:
            messagebox.showinfo('動画を指定', '解析設定で入力動画を指定してください。', parent=self)

    def _register_videos(self, videos, use_thumbnail=False):
        if not videos:
            return
        try:
            root = self.queue_output_root.get().strip()
            if not root:
                raise ValueError('予約の出力先を指定してください。')
            if Path(root).exists() and not Path(root).is_dir():
                raise ValueError('予約の出力先にはフォルダーを指定してください。')
            settings = self._collect()
            thumbnail = self.vars['THUMBNAIL_FILE'].get().strip() if use_thumbnail else None
            if thumbnail and not Path(thumbnail).is_file():
                raise ValueError(f'撮影日時用サムネイルが見つかりません。任意のため空欄でも登録できます。\n{thumbnail}')
            jobs = self.reservations.add(videos, settings, root, self._output_names, thumbnail)
        except (OSError, ValueError) as exc:
            messagebox.showerror('登録できません', str(exc), parent=self)
            return
        self._refresh_reservations()
        self._start_previews(jobs)
        self.reservation_tree.selection_set([job.id for job in jobs])
        self.reservation_tree.see(jobs[-1].id)
        self.tabs.select(self.queue_tab)
        self._append(f'予約に追加しました: {len(jobs)}件\n')

    def _refresh_reservations(self):
        tree = self.reservation_tree
        visible_jobs = [job for job in self.reservations.jobs if job.state != 'done']
        ids = {job.id for job in visible_jobs}
        for item in tree.get_children():
            if item not in ids:
                tree.delete(item)
                self._preview_photos.pop(item, None)
                self._preview_info.pop(item, None)
                self._preview_started.discard(item)
        for number, job in enumerate(visible_jobs, 1):
            values = (number, STATE_LABELS[job.state], str(job.output))
            photo = self._preview_photos.get(job.id, self._placeholder)
            if tree.exists(job.id):
                tree.item(job.id, text=job.video.name, values=values, image=photo)
            else:
                tree.insert('', 'end', iid=job.id, text=job.video.name, values=values, image=photo)
            tree.move(job.id, '', number - 1)
        counts = Counter(job.state for job in self.reservations.jobs)
        self.queue_summary.set(f'全{len(self.reservations.jobs)}件  /  完了 {counts["done"]}件  /  待機 {counts["pending"]}件'
            f'  /  解析中 {counts["running"]}件  /  失敗 {counts["failed"]}件')
        self._reservation_details()

    def _reservation_details(self):
        selected = self.reservation_tree.selection()
        job = self.reservations.find(selected[0]) if selected else None
        if job:
            info = self._preview_info.get(job.id, '')
            self.queue_details.set(f'入力: {job.video}\n出力: {job.output}\n'
                f'{info}  モデル: {job.settings.get("MODEL_MODE", "")} / YOLO: {job.settings.get("YOLO_MODEL", "")} '
                f'/ デバイス: {job.settings.get("DEVICE", "")}\n'
                f'{job.error[-400:] if job.error else "設定を確認すると、登録時に保存した解析条件を表示します。"}')
        else:
            self.queue_details.set('一覧から動画を選択すると詳細を表示します。' if self.reservation_tree.get_children()
                                   else '表示する予約はありません。「動画を追加…」で登録できます。')

    def _remove_reservations(self):
        ids = self.reservation_tree.selection()
        if not ids:
            return
        try:
            self.reservations.remove(ids)
        except OSError as exc:
            messagebox.showerror('予約を変更できません', str(exc), parent=self)
        self._refresh_reservations()

    def _move_reservation(self, delta):
        ids = self.reservation_tree.selection()
        if len(ids) != 1:
            return
        try:
            self.reservations.move(ids[0], delta)
        except OSError as exc:
            messagebox.showerror('予約を変更できません', str(exc), parent=self)
        self._refresh_reservations()
        self.reservation_tree.see(ids[0])

    def _retry_reservations(self):
        try:
            self.reservations.retry(self.reservation_tree.selection(), self._output_names)
        except OSError as exc:
            messagebox.showerror('予約を変更できません', str(exc), parent=self)
        self._refresh_reservations()

    def _show_reservation_settings(self):
        selected = self.reservation_tree.selection()
        job = self.reservations.find(selected[0]) if selected else None
        if not job:
            return
        window = tk.Toplevel(self)
        window.title(f'登録時の解析設定 — {job.video.name}')
        window.geometry('760x540')
        text = tk.Text(window, wrap='word', padx=10, pady=10)
        scroll = ttk.Scrollbar(window, command=text.yview)
        scroll.pack(side='right', fill='y')
        text.configure(yscrollcommand=scroll.set)
        text.pack(fill='both', expand=True)
        text.insert('1.0', json.dumps(job.settings, ensure_ascii=False, indent=2))
        text.configure(state='disabled')

    def _start_previews(self, jobs):
        targets = [(job.id, str(job.video)) for job in jobs
                   if job.state != 'done' and job.id not in self._preview_started]
        self._preview_started.update(job_id for job_id, _ in targets)
        if not targets:
            return

        def work():
            try:
                import cv2
                import numpy as np
            except ImportError:
                return
            for job_id, path in targets:
                cap = cv2.VideoCapture(path)
                try:
                    ok, frame = cap.read()
                    if not ok:
                        self.log_queue.put(('__PREVIEW__', job_id, None, 'プレビューを取得できません'))
                        continue
                    height, width = frame.shape[:2]
                    scale = min(104 / width, 58 / height)
                    thumb = cv2.resize(frame, (max(1, int(width * scale)), max(1, int(height * scale))))
                    image = np.full((58, 104, 3), 225, dtype=np.uint8)
                    y, x = (58 - thumb.shape[0]) // 2, (104 - thumb.shape[1]) // 2
                    image[y:y + thumb.shape[0], x:x + thumb.shape[1]] = thumb
                    success, png = cv2.imencode('.png', image)
                    self.log_queue.put(('__PREVIEW__', job_id, png.tobytes() if success else None, f'{width}×{height} px'))
                except Exception:
                    self.log_queue.put(('__PREVIEW__', job_id, None, 'プレビューを取得できません'))
                finally:
                    cap.release()
        threading.Thread(target=work, daemon=True).start()

    def _queue_start(self):
        if self.queue_active:
            return
        if self.reservations.next_pending() is None:
            messagebox.showinfo('予約がありません', '動画を予約に追加するか、失敗した予約を再予約してください。', parent=self)
            return
        self.tabs.select(self.queue_tab)
        self._queue_stop.clear()
        self.cancel_requested = False
        self.queue_active = True
        self.start_button.configure(state='disabled')
        self.cancel_button.configure(state='normal')
        self._next_reservation()

    def _next_reservation(self):
        self._next_token = None
        if not self.queue_active or self._queue_stop.is_set():
            self._finish_reservations()
            return
        job = self.reservations.next_pending()
        if job is None:
            self._finish_reservations()
            return
        self.current_job_id = job.id
        self.process = None
        self._job_tail = []
        try:
            if not job.video.is_file():
                raise ValueError(f'入力動画が見つかりません: {job.video}')
            if job.output.exists():
                # A previous attempt or another application may have created this output.
                destination = self.reservations.available_output(job.video, job.output.parent, job.id)
                set_output(job.settings, destination, self._output_names)
            config = self._reservation_base / '.analysis_jobs' / 'configs' / f'{job.id}.json'
            write_json(config, job.settings)
            (self._reservation_base / '.analysis_jobs' / 'logs').mkdir(parents=True, exist_ok=True)
            job.state, job.error = 'running', ''
            if not self._save_reservations():
                job.state = 'pending'
                self._finish_reservations()
                return
        except (OSError, ValueError) as exc:
            job.state, job.error = 'failed', str(exc)
            self._append(f'{job.video.name}: {exc}\n')
            if self._save_reservations():
                self._next_token = self.after(0, self._next_reservation)
            else:
                self._finish_reservations()
            self._refresh_reservations()
            return
        self.progress_value.set(0)
        self.progress_label.configure(text='0%')
        self.status.configure(text=f'解析中: {job.video.name}')
        self._append(f'\n--- 解析開始: {job.video}\n出力先: {job.output}\n')
        self._refresh_reservations()
        self.reservation_tree.see(job.id)
        threading.Thread(target=self._reservation_worker, args=(job.id, config), daemon=True).start()

    def _worker_command(self, config):
        return [sys.executable, '-u', '-X', 'utf8', str(self._reservation_base / 'gui.py'),
                '--analysis-worker', '--config', str(config)]

    def _reservation_worker(self, job_id, config):
        process = None
        try:
            log_path = self._reservation_base / '.analysis_jobs' / 'logs' / f'{job_id}.log'
            with log_path.open('w', encoding='utf-8') as log:
                if self._queue_stop.is_set():
                    self.log_queue.put(('__JOB_FINISHED__', job_id, -1))
                    return
                process = subprocess.Popen(self._worker_command(config), cwd=self._reservation_base,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                    errors='replace', bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                self.process = process
                if self._queue_stop.is_set() and process.poll() is None:
                    process.terminate()
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    self.log_queue.put(('__JOB_LOG__', job_id, line))
                code = process.wait()
                process.stdout.close()
                self.log_queue.put(('__JOB_FINISHED__', job_id, code))
        except Exception as exc:
            if process is not None and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                except OSError:
                    pass
            self.log_queue.put(('__JOB_LOG__', job_id, f'起動エラー: {exc}\n'))
            self.log_queue.put(('__JOB_FINISHED__', job_id, -1))
        finally:
            if process is not None and process.stdout is not None:
                process.stdout.close()

    def _queue_cancel(self):
        if not self.queue_active:
            return
        self.cancel_requested = True
        self._queue_stop.set()
        self.cancel_button.configure(state='disabled')
        self.status.configure(text='解析を中断しています。処理終了後、この動画を待機中へ戻します…')
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.terminate()
            except OSError:
                pass

    def _reservation_finished(self, job_id, code):
        if job_id != self.current_job_id:
            return
        job = self.reservations.find(job_id)
        if job:
            if code == 0:
                job.state, job.error = 'done', ''
                self.progress_value.set(100)
                self.progress_label.configure(text='100%')
            elif self._queue_stop.is_set():
                job.state, job.error = 'pending', ''
                self.reservations.prioritize_pending(job.id)
                self.progress_value.set(0)
                self.progress_label.configure(text='0%')
                self._append(f'{job.video.name} を中断し、待機中の先頭へ戻しました。\n')
            else:
                job.state = 'failed'
                job.error = f'終了コード {code}\n' + ''.join(self._job_tail)[-2000:]
        self.process = None
        self.current_job_id = None
        self._append(f'--- 終了コード: {code} ---\n')
        self._save_reservations()
        self._refresh_reservations()
        if self.queue_active and not self._queue_stop.is_set():
            self._next_token = self.after(0, self._next_reservation)
        else:
            self._finish_reservations()

    def _finish_reservations(self):
        self.queue_active = False
        self.current_job_id = None
        self.start_button.configure(state='normal')
        self.cancel_button.configure(state='disabled')
        self.status.configure(text='予約実行を中断しました。「解析を開始」で待機中の先頭から再実行します。'
                              if self._queue_stop.is_set() else '予約の解析が終了しました')
        self._refresh_reservations()
        if self._close_after_stop:
            self.destroy()

    def _queue_poll(self):
        self._poll_token = None
        for _ in range(300):
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break
            kind = item[0]
            if kind == '__PREVIEW__':
                _, job_id, data, info = item
                job = self.reservations.find(job_id)
                if job is not None and job.state != 'done':
                    if data:
                        self._preview_photos[job_id] = tk.PhotoImage(master=self, data=data)
                    self._preview_info[job_id] = info
                    self._refresh_reservations()
            elif kind == '__JOB_FINISHED__':
                self._reservation_finished(item[1], item[2])
                if self._close_after_stop and not self.queue_active:
                    return
            elif kind == '__JOB_LOG__' and item[1] == self.current_job_id:
                line = item[2]
                if line.startswith('PROGRESS:'):
                    try:
                        percent, phase = line.strip().split(':', 2)[1:]
                        percent = max(0, min(100, int(percent)))
                        self.progress_value.set(percent)
                        self.progress_label.configure(text=f'{percent}%')
                        job = self.reservations.find(item[1])
                        label = 'YOLO処理中' if phase == 'YOLO' else 'RTMLIB処理中'
                        self.status.configure(text=f'{job.video.name} — {label}')
                    except (ValueError, IndexError):
                        self._append(line)
                else:
                    self._job_tail.append(line)
                    self._job_tail = self._job_tail[-12:]
                    self._append(line)
        self._poll_token = self.after(100, self._poll)

    def _queue_close(self):
        if self.queue_active:
            if messagebox.askyesno('解析を中断して終了', '現在の解析を中断して終了しますか？ 現在の動画と後続の予約は待機中で保存されます。', parent=self):
                self._close_after_stop = True
                self._queue_cancel()
            return
        self.reservations.output_root = self.queue_output_root.get().strip() or self.reservations.output_root
        if self._save_reservations():
            self.destroy()

    def destroy(self):
        for name in ('_poll_token', '_next_token'):
            token = getattr(self, name, None)
            if token:
                self.after_cancel(token)
                setattr(self, name, None)
        super().destroy()
