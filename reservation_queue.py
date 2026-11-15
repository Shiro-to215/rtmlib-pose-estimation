"""Persistent reservations with a separate settings snapshot for each video."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from functools import wraps
import os
from pathlib import Path
import re
import tempfile
import threading
import uuid

STATES = {'pending', 'running', 'done', 'failed'}
_NUMERIC_SUFFIX_RE = re.compile(r'^(.+)_(\d+)$')


def transactional(method):
    @wraps(method)
    def update(self, *args, **kwargs):
        with self._lock:
            jobs, root = deepcopy(self.jobs), self.output_root
            try:
                return method(self, *args, **kwargs)
            except Exception:
                self.jobs, self.output_root = jobs, root
                raise
    return update


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                         suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def set_output(settings, destination, output_names):
    destination = Path(destination)
    settings.update(OUTPUT_ROOT=str(destination.parent), OUTPUT_FOLDER_NAME=destination.name)
    settings.update(output_names(destination))


@dataclass
class Reservation:
    settings: dict
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    state: str = 'pending'
    error: str = ''
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec='seconds'))

    @property
    def video(self):
        return Path(self.settings['INPUT_ROOT']) / self.settings['INPUT_VIDEO_NAME']

    @property
    def output(self):
        return Path(self.settings['OUTPUT_ROOT']) / self.settings['OUTPUT_FOLDER_NAME']


class ReservationQueue:
    def __init__(self, path, output_root):
        self._lock = threading.RLock()
        self.path = Path(path)
        self.output_root = str(output_root)
        self.jobs = []
        if self.path.exists():
            migrated = False
            resume_ids = []
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('jobs'), list):
                raise ValueError('予約ファイルの形式を読み取れません。')
            self.output_root = str(data.get('output_root', output_root))
            for record in data['jobs']:
                job = Reservation(**record)
                # Convert both old stop states and an unfinished previous run to pending.
                if job.state in {'running', 'stopped', 'interrupted'}:
                    if job.state == 'running':
                        resume_ids.append(job.id)
                    job.state, job.error = 'pending', ''
                    migrated = True
                if job.state not in STATES or not isinstance(job.settings, dict):
                    raise ValueError('予約の状態または設定が不正です。')
                if not isinstance(job.id, str) or len(job.id) != 32 or any(c not in '0123456789abcdef' for c in job.id):
                    raise ValueError('予約IDが不正です。')
                if not job.video.name or not job.output.name:
                    raise ValueError('入力動画または出力先が不正です。')
                self.jobs.append(job)
            if len({job.id for job in self.jobs}) != len(self.jobs):
                raise ValueError('予約IDが重複しています。')
            for job_id in reversed(resume_ids):
                self.prioritize_pending(job_id)
            if migrated:
                self.save()

    def save(self):
        with self._lock:
            write_json(self.path, {'version': 1, 'output_root': self.output_root,
                                   'jobs': [asdict(job) for job in self.jobs]})

    def snapshot_jobs(self):
        with self._lock:
            return list(self.jobs)

    def find(self, job_id):
        with self._lock:
            return next((job for job in self.jobs if job.id == job_id), None)

    def next_pending(self):
        with self._lock:
            return next((job for job in self.jobs if job.state == 'pending'), None)

    def prioritize_pending(self, job_id):
        """Put the interrupted job before other pending work; caller saves state/order together."""
        with self._lock:
            job = self.find(job_id)
            first = self.next_pending()
            if job is not None and job.state == 'pending' and first is not None:
                first_index = self.jobs.index(first)
                job_index = self.jobs.index(job)
                if job_index > first_index:
                    self.jobs.pop(job_index)
                    self.jobs.insert(first_index, job)

    def ensure_available_destination(self, destination, exclude_id=None):
        with self._lock:
            destination = Path(destination).expanduser().resolve()
            if not destination.name:
                raise ValueError('出力先フォルダを指定してください。')
            parent = destination.parent
            reserved = {
                str(job.output.resolve()).casefold()
                for job in self.jobs
                if job.id != exclude_id and job.state != 'done'
            }
            if not destination.exists() and str(destination).casefold() not in reserved:
                return destination
            match = _NUMERIC_SUFFIX_RE.match(destination.name)
            if match:
                base_name = match.group(1)
                number = max(2, int(match.group(2)) + 1)
            else:
                base_name = destination.name
                number = 2
            while True:
                candidate = parent / f'{base_name}_{number}'
                if not candidate.exists() and str(candidate).casefold() not in reserved:
                    return candidate
                number += 1

    def available_output(self, video, root, exclude_id=None):
        root = Path(root).expanduser().resolve()
        stem = Path(video).stem or 'video'
        return self.ensure_available_destination(root / stem, exclude_id=exclude_id)

    def set_output_root(self, output_root):
        with self._lock:
            self.output_root = str(output_root)
            self.save()

    @transactional
    def mark_job_running(self, job_id, output_names=None):
        job = self.find(job_id)
        if job is None:
            return None
        if output_names is not None and job.output.exists():
            safe_dest = self.ensure_available_destination(job.output, exclude_id=job.id)
            set_output(job.settings, safe_dest, output_names)
        job.state, job.error = 'running', ''
        self.save()
        return job

    @transactional
    def revert_job_pending(self, job_id, prioritize=True):
        job = self.find(job_id)
        if job is None:
            return None
        if job.state not in {'pending', 'running'}:
            return job
        job.state, job.error = 'pending', ''
        if prioritize:
            self.prioritize_pending(job.id)
        self.save()
        return job

    @transactional
    def mark_job_done(self, job_id):
        job = self.find(job_id)
        if job is None:
            return None
        job.state, job.error = 'done', ''
        self.save()
        return job

    @transactional
    def mark_job_failed(self, job_id, error_msg):
        job = self.find(job_id)
        if job is None:
            return None
        job.state, job.error = 'failed', str(error_msg)
        self.save()
        return job

    @transactional
    def add(self, videos, template, root, output_names, thumbnail=None, custom_destination=None):
        videos = [Path(video).expanduser().resolve() for video in videos]
        for video in videos:
            if not video.is_file():
                raise ValueError(f'入力動画が見つかりません。\n{video}')
        created = []
        for index, video in enumerate(videos):
            settings = deepcopy(template)
            settings.update(INPUT_ROOT=str(video.parent), INPUT_VIDEO_NAME=video.name,
                            THUMBNAIL_ROOT='', THUMBNAIL_IMAGE_NAME='')
            if thumbnail and len(videos) == 1:
                thumb_path = Path(thumbnail).expanduser().resolve()
                settings['THUMBNAIL_ROOT'] = str(thumb_path.parent)
                settings['THUMBNAIL_IMAGE_NAME'] = thumb_path.name
            if custom_destination is not None and len(videos) == 1 and index == 0:
                dest = self.ensure_available_destination(custom_destination)
            else:
                dest = self.available_output(video, root)
            set_output(settings, dest, output_names)
            job = Reservation(settings=settings)
            self.jobs.append(job)
            created.append(job)
        if root:
            self.output_root = str(Path(root).expanduser().resolve())
        self.save()
        return created

    @transactional
    def update_job(self, job_id, settings, destination, output_names, reset_failed=False):
        job = self.find(job_id)
        if job is None:
            raise ValueError('対象の予約が見つかりません。')
        if job.state in {'running', 'done'}:
            raise ValueError('解析中または完了済みの予約は設定を変更できません。')
        dest = Path(destination).expanduser().resolve()
        if not dest.name:
            raise ValueError('出力先フォルダを指定してください。')
        reserved = {
            str(other.output.resolve()).casefold()
            for other in self.jobs
            if other.id != job_id and other.state != 'done'
        }
        if str(dest).casefold() in reserved:
            raise ValueError('指定された出力先フォルダは他の予約で既に使用されています。別のフォルダ名を指定してください。')
        new_settings = deepcopy(settings)
        set_output(new_settings, dest, output_names)
        job.settings = new_settings
        if reset_failed and job.state == 'failed':
            job.state, job.error = 'pending', ''
        self.save()
        return job

    @transactional
    def remove(self, ids):
        self.jobs = [job for job in self.jobs if job.id not in ids or job.state == 'running']
        self.save()

    @transactional
    def move(self, job_id, delta):
        if delta not in (-1, 1):
            raise ValueError('移動方向は上または下を指定してください。')
        job = self.find(job_id)
        if job is None or job.state not in {'pending', 'failed'}:
            return
        index = self.jobs.index(job)
        other = index + delta
        while 0 <= other < len(self.jobs):
            if self.jobs[other].state in {'pending', 'failed'}:
                self.jobs[index], self.jobs[other] = self.jobs[other], self.jobs[index]
                self.save()
                return
            other += delta

    @transactional
    def reorder_job(self, job_id, target_visible_index):
        """Move a pending/failed job directly to target_visible_index among visible queue items."""
        visible_slots = [i for i, j in enumerate(self.jobs) if j.state in {'pending', 'failed'}]
        job = self.find(job_id)
        if job is None or job.state not in {'pending', 'failed'} or not visible_slots:
            return
        visible_jobs = [self.jobs[i] for i in visible_slots]
        current_pos = visible_jobs.index(job)
        clamped_target = max(0, min(int(target_visible_index), len(visible_jobs) - 1))
        if current_pos == clamped_target:
            return
        visible_jobs.pop(current_pos)
        visible_jobs.insert(clamped_target, job)
        for slot_idx, moved_job in zip(visible_slots, visible_jobs):
            self.jobs[slot_idx] = moved_job
        self.save()

    @transactional
    def retry(self, ids, output_names):
        for job in self.jobs:
            if job.id in ids and job.state not in {'pending', 'running'}:
                set_output(job.settings, self.ensure_available_destination(job.output, job.id), output_names)
                job.state, job.error = 'pending', ''
        self.save()
