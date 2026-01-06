import os
import subprocess
import json
from pathlib import Path
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TDRC
import requests

def check_ytdlp():
    """Check apakah yt-dlp sudah terinstall"""
    try:
        result = subprocess.run(['yt-dlp', '--version'], 
                              capture_output=True, 
                              text=True)
        if result.returncode == 0:
            return True
    except FileNotFoundError:
        pass
    return False

def check_ffmpeg():
    """Check apakah ffmpeg sudah terinstall"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, 
                              text=True)
        if result.returncode == 0:
            return True
    except FileNotFoundError:
        pass
    return False

def get_video_info(url):
    """Dapatkan informasi video dari URL"""
    try:
        print("\n🔍 Mengambil informasi video...")
        
        command = [
            'yt-dlp',
            '--dump-json',
            '--no-playlist',
            url
        ]
        
        result = subprocess.run(command, 
                              capture_output=True, 
                              text=True,
                              timeout=30)
        
        if result.returncode != 0:
            print(f"✗ Error: {result.stderr}")
            return None
        
        info = json.loads(result.stdout)
        return info
        
    except subprocess.TimeoutExpired:
        print("✗ Timeout saat mengambil informasi video")
        return None
    except json.JSONDecodeError:
        print("✗ Gagal parsing informasi video")
        return None
    except Exception as e:
        print(f"✗ Error: {e}")
        return None

def format_filesize(bytes_size):
    """Format ukuran file ke MB atau GB"""
    if bytes_size is None:
        return "Unknown"
    
    mb = bytes_size / (1024 * 1024)
    if mb < 1024:
        return f"{mb:.2f} MB"
    else:
        gb = mb / 1024
        return f"{gb:.2f} GB"

def get_available_formats(info):
    """Dapatkan daftar format yang tersedia"""
    formats = info.get('formats', [])
    
    audio_formats = []
    video_formats = []
    
    for fmt in formats:
        format_id = fmt.get('format_id')
        ext = fmt.get('ext')
        
        # Audio only
        if fmt.get('vcodec') == 'none' and fmt.get('acodec') != 'none':
            audio_formats.append({
                'id': format_id,
                'ext': ext,
                'abr': fmt.get('abr', 0),
                'filesize': fmt.get('filesize') or fmt.get('filesize_approx'),
                'format_note': fmt.get('format_note', '')
            })
        
        # Video (dengan atau tanpa audio)
        elif fmt.get('vcodec') != 'none':
            video_formats.append({
                'id': format_id,
                'ext': ext,
                'resolution': fmt.get('resolution', 'Unknown'),
                'fps': fmt.get('fps', 0),
                'vcodec': fmt.get('vcodec', ''),
                'acodec': fmt.get('acodec', 'none'),
                'filesize': fmt.get('filesize') or fmt.get('filesize_approx'),
                'format_note': fmt.get('format_note', ''),
                'height': fmt.get('height', 0)
            })
    
    # Sort audio by bitrate (highest first)
    audio_formats.sort(key=lambda x: x['abr'], reverse=True)
    
    # Sort video by height (highest first)
    video_formats.sort(key=lambda x: x['height'], reverse=True)
    
    return audio_formats, video_formats

def download_thumbnail(url):
    """Download thumbnail"""
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.content
    except:
        pass
    return None

def embed_thumbnail_to_mp3(mp3_path, thumbnail_data, title, artist, year=None):
    """Embed thumbnail ke MP3"""
    try:
        print("🖼️  Meng-embed thumbnail ke MP3...")
        
        audio = MP3(mp3_path)
        
        if audio.tags is None:
            audio.add_tags()
        
        audio.tags.delall('APIC')
        
        audio.tags.add(
            APIC(
                encoding=3,
                mime='image/jpeg',
                type=3,
                desc='Cover',
                data=thumbnail_data
            )
        )
        
        audio.tags.add(TIT2(encoding=3, text=title))
        audio.tags.add(TPE1(encoding=3, text=artist))
        audio.tags.add(TALB(encoding=3, text=title))
        
        if year:
            audio.tags.add(TDRC(encoding=3, text=str(year)))
        
        audio.save(v2_version=3)
        
        print("✓ Thumbnail berhasil di-embed!")
        return True
        
    except Exception as e:
        print(f"⚠️  Gagal embed thumbnail: {e}")
        return False

def download_audio(url, output_path="downloads"):
    """Download audio dalam format MP3"""
    try:
        Path(output_path).mkdir(parents=True, exist_ok=True)
        
        # Dapatkan info video
        info = get_video_info(url)
        if not info:
            return
        
        title = info.get('title', 'Unknown')
        uploader = info.get('uploader', 'Unknown')
        duration = info.get('duration', 0)
        thumbnail_url = info.get('thumbnail')
        
        print(f"\n📹 Judul: {title}")
        print(f"👤 Uploader: {uploader}")
        print(f"⏱️  Durasi: {duration // 60}:{duration % 60:02d}")
        print(f"🌐 Platform: {info.get('extractor', 'Unknown')}")
        
        # Dapatkan format audio
        audio_formats, _ = get_available_formats(info)
        
        if not audio_formats:
            print("\n✗ Tidak ada format audio yang tersedia")
            return
        
        # Tampilkan pilihan audio
        print("\n🎵 Kualitas Audio Tersedia:")
        print("-" * 60)
        
        # Limit to top 10 formats
        display_formats = audio_formats[:10]
        
        for idx, fmt in enumerate(display_formats, 1):
            abr = f"{fmt['abr']:.0f}kbps" if fmt['abr'] else "Unknown"
            size = format_filesize(fmt['filesize'])
            note = fmt['format_note']
            print(f"{idx}. {abr} - {fmt['ext'].upper()} ({size}) {note}")
        
        # Pilih kualitas
        while True:
            try:
                choice = input(f"\n🎯 Pilih kualitas (1-{len(display_formats)}, Enter=terbaik): ").strip()
                if not choice:
                    choice = 1
                    break
                choice = int(choice)
                if 1 <= choice <= len(display_formats):
                    break
                print("❌ Pilihan tidak valid!")
            except ValueError:
                print("❌ Masukkan angka yang valid!")
        
        selected_format = display_formats[choice - 1]
        format_id = selected_format['id']
        
        print(f"\n✓ Dipilih: {selected_format['abr']:.0f}kbps")
        
        # Bersihkan nama file
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = safe_title[:100]
        if not safe_title:
            safe_title = "audio"
        
        output_file = os.path.join(output_path, f"{safe_title}.mp3")
        
        # Download dengan yt-dlp
        print("\n📥 Mendownload audio...")
        
        command = [
            'yt-dlp',
            '-f', format_id,
            '--extract-audio',
            '--audio-format', 'mp3',
            '--audio-quality', '0',  # Best quality
            '-o', output_file,
            '--no-playlist',
            '--progress',
            url
        ]
        
        result = subprocess.run(command)
        
        if result.returncode != 0:
            print("\n✗ Download gagal!")
            return
        
        print("\n✓ Download selesai!")
        
        # Download dan embed thumbnail
        if thumbnail_url and os.path.exists(output_file):
            print("\n📥 Mengunduh thumbnail...")
            thumbnail_data = download_thumbnail(thumbnail_url)
            
            if thumbnail_data:
                year = info.get('upload_date')
                if year and len(year) >= 4:
                    year = year[:4]
                else:
                    year = None
                
                embed_thumbnail_to_mp3(output_file, thumbnail_data, title, uploader, year)
        
        # Info file
        if os.path.exists(output_file):
            filesize = os.path.getsize(output_file)
            print(f"\n✅ BERHASIL!")
            print(f"📁 Lokasi: {output_file}")
            print(f"💾 Ukuran: {format_filesize(filesize)}")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

def download_video(url, output_path="downloads"):
    """Download video dalam format MP4"""
    try:
        Path(output_path).mkdir(parents=True, exist_ok=True)
        
        # Dapatkan info video
        info = get_video_info(url)
        if not info:
            return
        
        title = info.get('title', 'Unknown')
        uploader = info.get('uploader', 'Unknown')
        duration = info.get('duration', 0)
        
        print(f"\n📹 Judul: {title}")
        print(f"👤 Uploader: {uploader}")
        print(f"⏱️  Durasi: {duration // 60}:{duration % 60:02d}")
        print(f"🌐 Platform: {info.get('extractor', 'Unknown')}")
        
        # Dapatkan format video
        _, video_formats = get_available_formats(info)
        
        if not video_formats:
            print("\n✗ Tidak ada format video yang tersedia")
            return
        
        # Filter dan deduplikasi format
        seen_resolutions = {}
        filtered_formats = []
        
        for fmt in video_formats:
            resolution = fmt['resolution']
            height = fmt['height']
            
            # Prioritas: dengan audio > tanpa audio, filesize lebih besar
            key = f"{height}p"
            
            if key not in seen_resolutions:
                seen_resolutions[key] = fmt
                filtered_formats.append(fmt)
            else:
                # Ganti jika format baru lebih baik (punya audio atau filesize lebih besar)
                existing = seen_resolutions[key]
                if (fmt['acodec'] != 'none' and existing['acodec'] == 'none') or \
                   (fmt.get('filesize', 0) or 0) > (existing.get('filesize', 0) or 0):
                    seen_resolutions[key] = fmt
                    # Replace in filtered_formats
                    for i, f in enumerate(filtered_formats):
                        if f['height'] == height:
                            filtered_formats[i] = fmt
                            break
        
        # Tampilkan pilihan video
        print("\n🎬 Kualitas Video Tersedia:")
        print("-" * 70)
        
        for idx, fmt in enumerate(filtered_formats, 1):
            has_audio = "🔊" if fmt['acodec'] != 'none' else "🔇"
            fps = f"@{fmt['fps']}fps" if fmt['fps'] else ""
            size = format_filesize(fmt['filesize'])
            note = fmt['format_note']
            print(f"{idx}. {fmt['resolution']} {fps} {has_audio} - {fmt['ext'].upper()} ({size}) {note}")
        
        # Pilih kualitas
        while True:
            try:
                choice = input(f"\n🎯 Pilih kualitas (1-{len(filtered_formats)}, Enter=terbaik): ").strip()
                if not choice:
                    choice = 1
                    break
                choice = int(choice)
                if 1 <= choice <= len(filtered_formats):
                    break
                print("❌ Pilihan tidak valid!")
            except ValueError:
                print("❌ Masukkan angka yang valid!")
        
        selected_format = filtered_formats[choice - 1]
        format_id = selected_format['id']
        has_audio = selected_format['acodec'] != 'none'
        
        print(f"\n✓ Dipilih: {selected_format['resolution']} ({selected_format['ext'].upper()})")
        
        # Bersihkan nama file
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = safe_title[:100]
        if not safe_title:
            safe_title = "video"
        
        output_file = os.path.join(output_path, f"{safe_title}.mp4")
        
        # Download dengan yt-dlp
        print("\n📥 Mendownload video...")
        
        if has_audio:
            # Video sudah punya audio, download langsung
            command = [
                'yt-dlp',
                '-f', format_id,
                '-o', output_file,
                '--no-playlist',
                '--progress',
                url
            ]
        else:
            # Video tanpa audio, merge dengan audio terbaik
            print("ℹ️  Video akan digabung dengan audio terbaik...")
            command = [
                'yt-dlp',
                '-f', f'{format_id}+bestaudio',
                '--merge-output-format', 'mp4',
                '-o', output_file,
                '--no-playlist',
                '--progress',
                url
            ]
        
        result = subprocess.run(command)
        
        if result.returncode != 0:
            print("\n✗ Download gagal!")
            return
        
        print("\n✓ Download selesai!")
        
        # Info file
        if os.path.exists(output_file):
            filesize = os.path.getsize(output_file)
            print(f"\n✅ BERHASIL!")
            print(f"📁 Lokasi: {output_file}")
            print(f"💾 Ukuran: {format_filesize(filesize)}")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

def show_supported_sites():
    """Tampilkan beberapa website yang didukung"""
    sites = [
        "YouTube", "Facebook", "Instagram", "Twitter/X", "TikTok",
        "Vimeo", "Dailymotion", "Reddit", "Twitch", "Streamable",
        "SoundCloud", "Mixcloud", "Bandcamp", "Pinterest", "LinkedIn",
        "9GAG", "Imgur", "Flickr", "Tumblr", "dan 1000+ website lainnya!"
    ]
    
    print("\n🌐 Website yang Didukung:")
    print("-" * 70)
    for i in range(0, len(sites), 4):
        row = sites[i:i+4]
        print("  " + " | ".join(f"{site:<18}" for site in row))
    print()

def main():
    """Fungsi utama program"""
    print("=" * 70)
    print("  Universal Video Downloader - Support 1000+ Websites!")
    print("=" * 70)
    
    # Check dependencies
    print("\n🔍 Memeriksa dependencies...")
    
    ytdlp_ok = check_ytdlp()
    ffmpeg_ok = check_ffmpeg()
    
    if not ytdlp_ok:
        print("\n❌ yt-dlp belum terinstall!")
        print("   Install dengan: pip install yt-dlp")
        print("   Atau download: https://github.com/yt-dlp/yt-dlp")
        return
    
    if not ffmpeg_ok:
        print("\n⚠️  ffmpeg belum terinstall!")
        print("   Beberapa fitur mungkin tidak bekerja optimal")
        print("   Download: https://ffmpeg.org/download.html")
        print()
    else:
        print("✓ yt-dlp dan ffmpeg terdeteksi!")
    
    # Tampilkan website yang didukung
    show_supported_sites()
    
    # Input URL
    url = input("🔎 Masukkan URL (YouTube, Instagram, Facebook, dll): ").strip()
    
    if not url:
        print("❌ URL tidak boleh kosong!")
        return
    
    # Pilih format
    print("\n📋 Pilih Format Download:")
    print("1. 🎵 MP3 (Audio Only)")
    print("2. 🎬 MP4 (Video)")
    
    while True:
        try:
            format_choice = input("\n🎯 Pilih format (1/2): ").strip()
            if format_choice in ['1', '2']:
                break
            print("❌ Pilihan tidak valid!")
        except:
            print("❌ Masukkan angka yang valid!")
    
    # Input folder tujuan
    output = input("\n📁 Folder tujuan (Enter = 'downloads'): ").strip()
    if not output:
        output = "downloads"
    
    # Proses download
    print()
    if format_choice == '1':
        download_audio(url, output)
    else:
        download_video(url, output)
    
    # Tanya apakah ingin mengunduh lagi
    print("\n" + "=" * 70)
    lagi = input("🔄 Unduh video lain? (y/n): ").strip().lower()
    if lagi == 'y':
        print("\n")
        main()
    else:
        print("\n👋 Terima kasih telah menggunakan Universal Video Downloader!")

if __name__ == "__main__":
    main()
