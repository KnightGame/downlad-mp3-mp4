# app.py - Flask Backend (Railway Ready) - FIXED v2
from flask import Flask, render_template, request, jsonify, send_file
import subprocess
import json
import os
from pathlib import Path
import uuid
from threading import Thread
import time

app = Flask(__name__)

# Konfigurasi
DOWNLOAD_FOLDER = 'downloads'
Path(DOWNLOAD_FOLDER).mkdir(exist_ok=True)

# Store download progress
download_progress = {}

def check_dependencies():
    """Check yt-dlp dan ffmpeg"""
    ytdlp_ok = False
    ffmpeg_ok = False
    
    try:
        subprocess.run(['yt-dlp', '--version'], capture_output=True, timeout=5)
        ytdlp_ok = True
    except:
        pass
    
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        ffmpeg_ok = True
    except:
        pass
    
    return ytdlp_ok, ffmpeg_ok

@app.route('/')
def index():
    """Halaman utama"""
    return render_template('index.html')

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'message': 'Server is running'})

@app.route('/check-dependencies')
def check_deps():
    """Check dependencies"""
    ytdlp, ffmpeg = check_dependencies()
    return jsonify({
        'ytdlp': ytdlp,
        'ffmpeg': ffmpeg
    })

@app.route('/get-info', methods=['POST'])
def get_info():
    """Dapatkan info video dari URL"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL tidak boleh kosong'}), 400
        
        # Jalankan yt-dlp untuk dapatkan info
        command = [
            'yt-dlp',
            '--dump-json',
            '--no-playlist',
            url
        ]
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return jsonify({'error': 'Gagal mengambil informasi video'}), 400
        
        info = json.loads(result.stdout)
        
        # Parse formats
        formats = info.get('formats', [])
        
        # Debug: Log total formats
        print(f"Total formats: {len(formats)}")
        
        audio_formats = []
        video_formats = []
        
        # Filter audio formats - SANGAT PERMISIF
        for fmt in formats:
            vcodec = fmt.get('vcodec', 'none')
            acodec = fmt.get('acodec', 'none')
            
            # Audio: TIDAK ada video codec (none/null) DAN ADA audio codec
            is_audio_only = (vcodec in ['none', None]) and (acodec not in ['none', None, ''])
            
            if is_audio_only:
                # Ambil bitrate dari berbagai sumber
                abr = fmt.get('abr') or fmt.get('tbr') or fmt.get('asr', 0) / 1000 or 128
                
                # Ambil filesize dari berbagai sumber
                filesize = fmt.get('filesize') or fmt.get('filesize_approx') or 0
                
                audio_formats.append({
                    'id': fmt.get('format_id'),
                    'ext': fmt.get('ext', 'unknown'),
                    'abr': abr,
                    'filesize': filesize,
                    'note': fmt.get('format_note', ''),
                    'acodec': acodec
                })
        
        print(f"Audio formats found: {len(audio_formats)}")
        
        # Filter video formats
        for fmt in formats:
            vcodec = fmt.get('vcodec', 'none')
            acodec = fmt.get('acodec', 'none')
            
            # Video: ADA video codec (bukan none/null)
            is_video = vcodec not in ['none', None, '']
            
            if is_video:
                height = fmt.get('height', 0)
                width = fmt.get('width', 0)
                fps = fmt.get('fps') or 30
                
                # Ambil filesize dari berbagai sumber
                filesize = fmt.get('filesize') or fmt.get('filesize_approx') or 0
                
                # Check has audio
                has_audio = acodec not in ['none', None, '']
                
                # Resolution
                if height > 0:
                    resolution = f"{width}x{height}" if width > 0 else f"{height}p"
                else:
                    resolution = fmt.get('resolution', 'Unknown')
                
                video_formats.append({
                    'id': fmt.get('format_id'),
                    'ext': fmt.get('ext', 'mp4'),
                    'resolution': resolution,
                    'fps': fps,
                    'vcodec': vcodec,
                    'acodec': acodec,
                    'has_audio': has_audio,
                    'filesize': filesize,
                    'note': fmt.get('format_note', ''),
                    'height': height,
                    'width': width
                })
        
        print(f"Video formats found: {len(video_formats)}")
        
        # Sort audio by bitrate (highest first)
        audio_formats.sort(key=lambda x: x.get('abr', 0) or 0, reverse=True)
        
        # Deduplikasi video formats berdasarkan resolution
        seen_resolutions = {}
        filtered_video_formats = []
        
        for fmt in video_formats:
            height = fmt.get('height', 0)
            if height == 0:
                continue
            
            key = f"{height}p"
            
            if key not in seen_resolutions:
                seen_resolutions[key] = fmt
                filtered_video_formats.append(fmt)
            else:
                # Prioritas: dengan audio > tanpa audio, filesize lebih besar
                existing = seen_resolutions[key]
                current_has_audio = fmt['has_audio']
                existing_has_audio = existing['has_audio']
                current_size = fmt.get('filesize', 0) or 0
                existing_size = existing.get('filesize', 0) or 0
                
                # Ganti jika format baru lebih baik
                should_replace = False
                
                # Prioritas 1: Ada audio lebih baik
                if current_has_audio and not existing_has_audio:
                    should_replace = True
                # Prioritas 2: Sama-sama ada/tidak ada audio, pilih yang lebih besar
                elif current_has_audio == existing_has_audio and current_size > existing_size:
                    should_replace = True
                
                if should_replace:
                    seen_resolutions[key] = fmt
                    # Replace in filtered list
                    for i, f in enumerate(filtered_video_formats):
                        if f.get('height') == height:
                            filtered_video_formats[i] = fmt
                            break
        
        # Sort video by height (highest first)
        filtered_video_formats.sort(key=lambda x: x.get('height', 0) or 0, reverse=True)
        
        # Limit jumlah format
        audio_formats = audio_formats[:10]
        filtered_video_formats = filtered_video_formats[:15]
        
        # Debug output
        print(f"Final audio formats: {len(audio_formats)}")
        print(f"Final video formats: {len(filtered_video_formats)}")
        
        # Response
        response = {
            'title': info.get('title', 'Unknown'),
            'uploader': info.get('uploader', 'Unknown'),
            'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail'),
            'platform': info.get('extractor', 'Unknown'),
            'audio_formats': audio_formats,
            'video_formats': filtered_video_formats
        }
        
        return jsonify(response)
        
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Timeout saat mengambil informasi'}), 408
    except json.JSONDecodeError as e:
        return jsonify({'error': f'Error parsing video info: {str(e)}'}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/download', methods=['POST'])
def download():
    """Download video/audio"""
    try:
        data = request.json
        url = data.get('url')
        format_type = data.get('type')
        format_id = data.get('format_id')
        title = data.get('title', 'download')
        has_audio = data.get('has_audio', True)
        
        print(f"Download request: type={format_type}, format_id={format_id}, has_audio={has_audio}")
        
        if not all([url, format_type, format_id]):
            return jsonify({'error': 'Data tidak lengkap'}), 400
        
        download_id = str(uuid.uuid4())
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = safe_title[:100] or 'download'
        
        thread = Thread(
            target=download_file,
            args=(download_id, url, format_type, format_id, safe_title, has_audio)
        )
        thread.start()
        
        return jsonify({
            'download_id': download_id,
            'message': 'Download dimulai'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def download_file(download_id, url, format_type, format_id, safe_title, has_audio):
    """Background task untuk download"""
    try:
        download_progress[download_id] = {
            'status': 'downloading',
            'progress': 0,
            'message': 'Memulai download...'
        }
        
        if format_type == 'audio':
            # Download audio
            output_file = os.path.join(DOWNLOAD_FOLDER, f"{download_id}_{safe_title}.mp3")
            
            command = [
                'yt-dlp',
                '-f', format_id,
                '--extract-audio',
                '--audio-format', 'mp3',
                '--audio-quality', '0',
                '-o', output_file,
                '--no-playlist',
                '--newline',
                url
            ]
        else:
            # Download video
            output_file = os.path.join(DOWNLOAD_FOLDER, f"{download_id}_{safe_title}.mp4")
            
            if has_audio:
                # Video sudah punya audio, download langsung
                command = [
                    'yt-dlp',
                    '-f', format_id,
                    '-o', output_file,
                    '--no-playlist',
                    '--newline',
                    url
                ]
            else:
                # Video tanpa audio, merge dengan audio terbaik
                command = [
                    'yt-dlp',
                    '-f', f'{format_id}+bestaudio/best',
                    '--merge-output-format', 'mp4',
                    '-o', output_file,
                    '--no-playlist',
                    '--newline',
                    url
                ]
        
        print(f"Running command: {' '.join(command)}")
        
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        for line in process.stdout:
            print(line.strip())  # Debug output
            if '[download]' in line and '%' in line:
                try:
                    parts = line.split()
                    for part in parts:
                        if '%' in part:
                            progress = float(part.replace('%', ''))
                            download_progress[download_id]['progress'] = progress
                            break
                except:
                    pass
        
        process.wait()
        
        if process.returncode == 0 and os.path.exists(output_file):
            filesize = os.path.getsize(output_file)
            download_progress[download_id] = {
                'status': 'completed',
                'progress': 100,
                'message': 'Download selesai!',
                'file': output_file,
                'filename': os.path.basename(output_file),
                'filesize': filesize
            }
        else:
            download_progress[download_id] = {
                'status': 'error',
                'progress': 0,
                'message': 'Download gagal'
            }
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        download_progress[download_id] = {
            'status': 'error',
            'progress': 0,
            'message': str(e)
        }

@app.route('/progress/<download_id>')
def get_progress(download_id):
    """Dapatkan progress download"""
    progress = download_progress.get(download_id, {
        'status': 'not_found',
        'progress': 0,
        'message': 'Download tidak ditemukan'
    })
    return jsonify(progress)

@app.route('/download-file/<download_id>')
def download_file_route(download_id):
    """Download file yang sudah selesai"""
    progress = download_progress.get(download_id)
    
    if not progress or progress['status'] != 'completed':
        return 'File tidak ditemukan', 404
    
    file_path = progress['file']
    
    if not os.path.exists(file_path):
        return 'File tidak ditemukan', 404
    
    def cleanup():
        time.sleep(5)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            if download_id in download_progress:
                del download_progress[download_id]
        except:
            pass
    
    Thread(target=cleanup).start()
    
    return send_file(
        file_path,
        as_attachment=True,
        download_name=progress['filename']
    )

# PENTING: Untuk Railway, jangan gunakan if __name__ == '__main__'
# Gunicorn akan langsung import app object
