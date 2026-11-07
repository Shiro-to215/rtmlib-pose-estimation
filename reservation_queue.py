"""Persistent reservations with a separate settings snapshot for each video."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from functools import wraps
import os
from pathlib import Path
import tempfile
import uuid

STATES = {'pending', 'running', 'done', 'failed'}


def transactional(method):
    @wraps(method)
    def update(self, *args, **kwargs):
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
        write_json(self.path, {'version': 1, 'output_root': self.output_root,
                               'jobs': [asdict(job) for job in self.jobs]})

    def find(self, job_id):
        return next((job for job in self.jobs if job.id == job_id), None)

    def next_pending(self):
        return next((job for job in self.jobs if job.state == 'pending'), None)

    def prioritize_pending(self, job_id):
        """Put the interrupted job before other pending work; caller saves state/order together."""
        job = self.find(job_id)
        first = self.next_pending()
        if job is not None and job.state == 'pending' and first is not None:
            first_index = self.jobs.index(first)
            job_index = self.jobs.index(job)
            if job_index > first_index:
                self.jobs.pop(job_index)
                self.jobs.insert(first_index, job)

    def available_output(self, video, root, exclude_id=None):
        root = Path(root).expanduser().resolve()
        reserved = {str(job.output.resolve()).casefold() for job in self.jobs if job.id != exclude_id}
        stem = Path(video).stem or 'video'
        number = 1
        while True:
            candidate = root / (stem if number == 1 else f'{stem}_{number}')
            if not candidate.exists() and str(candidate).casefold() not in reserved:
                return candidate
            number += 1

    @transactional
    def add(self, videos, template, root, output_names, thumbnail=None):
        videos = [Path(video).expanduser().resolve() for video in videos]
        for video in videos:
            if not video.is_file():
                raise ValueError(f'入力動画が見つかりません。\n{video}')
        created = []
        for video in videos:
            settings = deepcopy(template)
            settings.update(INPUT_ROOT=str(video.parent), INPUT_VIDEO_NAME=video.name,
                            THUMBNAIL_ROOT='', THUMBNAIL_IMAGE_NAME='')
            if thumbnail:
                settings['THUMBNAIL_ROOT'] = str(Path(thumbnail).parent)
                settings['THUMBNAIL_IMAGE_NAME'] = Path(thumbnail).name
            set_output(settings, self.available_output(video, root), output_names)
            job = Reservation(settings=settings)
            self.jobs.append(job)
            created.append(job)
        self.output_root = str(Path(root).expanduser().resolve())
        self.save()
        return created

    @transactional
    def remove(self, ids):
        self.jobs = [job for job in self.jobs if job.id not in ids or job.state == 'running']
        self.save()

    @transactional
    def move(self, job_id, delta):
        if delta not in (-1, 1):
            raise ValueError('移動方向は上または下を指定してください。')
        job = self.find(job_id)
        if job is None or job.state != 'pending':
            return
        index = self.jobs.index(job)
        other = index + delta
        while 0 <= other < len(self.jobs):
            if self.jobs[other].state == 'pending':
                self.jobs[index], self.jobs[other] = self.jobs[other], self.jobs[index]
                self.save()
                return
            other += delta

    @transactional
    def retry(self, ids, output_names):
        for job in self.jobs:
            if job.id in ids and job.state not in {'pending', 'running'}:
                root = job.output.parent
                set_output(job.settings, self.available_output(job.video, root, job.id), output_names)
                job.state, job.error = 'pending', ''
        self.save()
