import os
import discord
import wavelink
from wavelink.websocket import Websocket
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
IMAGE_PATHS = ["image.png", "image.jpg", "image.jpeg"]  # Görseli bu isimlerden biriyle botun yanına koy
IMAGE_URL = os.getenv("IMAGE_URL", "")  # image.png yoksa bu link kullanılır
STATUS_NAME = "Comolokko"  # Botun altında "Comolokko izliyor" olarak görünür

MESSAGE_TEXT = """https://www.tiktok.com/@comolokko.46
https://www.instagram.com/hturk46
https://kick.com/comolokko-46

https://www.tiktok.com/@raiwennxd
https://kick.com/raiwennxd"""

# ---------- Lavalink (ses sunucusu) ayarları ----------
# Halka açık bir Lavalink v4 sunucusu (senin JS botundaki ile aynı).
# Kendi sunucunu kullanmak istersen .env dosyasına LAVALINK_URI ve
# LAVALINK_PASSWORD yazabilirsin, o zaman ilk o denenir.
LAVALINK_NODES = [
    ("ajie", "https://lava-v4.ajieblogs.eu.org:443", "https://dsc.gg/ajidevserver"),
]
if os.getenv("LAVALINK_URI"):
    LAVALINK_NODES.insert(
        0, ("ozel", os.getenv("LAVALINK_URI"), os.getenv("LAVALINK_PASSWORD", ""))
    )

# --- Yama: /v4/info hatasını atla ---
# Bu sunucu /v4/info adresine JSON yerine HTML hata sayfası döndürüyor.
# Wavelink bu hatada bağlantıyı koparıp "hazır" olayını hiç göndermiyordu.
# Hatayı yutup bağlantıya devam ediyoruz (JS botundaki "NODE PATCH" ile aynı fikir).
_orijinal_update_node = Websocket._update_node


async def _guvenli_update_node(self):
    try:
        await _orijinal_update_node(self)
    except Exception as e:
        print(f"[yama] /v4/info atlandı ({type(e).__name__}), bağlantı devam ediyor.")


Websocket._update_node = _guvenli_update_node


def build_message():
    """Embed'i ve (varsa) görsel dosyasını hazırlar."""
    embed = discord.Embed(description=MESSAGE_TEXT, color=0x0A0A0C)
    file = None

    found = next((p for p in IMAGE_PATHS if os.path.exists(p)), None)
    if found:
        file = discord.File(found, filename=found)
        embed.set_image(url=f"attachment://{found}")
    elif IMAGE_URL:
        embed.set_image(url=IMAGE_URL)

    return embed, file


class Bot(discord.Client):
    def __init__(self):
        super().__init__(
            intents=discord.Intents.default(),
            activity=discord.Activity(
                type=discord.ActivityType.watching, name=STATUS_NAME
            ),
        )
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        nodes = [
            wavelink.Node(identifier=name, uri=uri, password=password)
            for name, uri, password in LAVALINK_NODES
        ]
        try:
            await wavelink.Pool.connect(nodes=nodes, client=self, cache_capacity=100)
        except Exception as e:
            print(f"Lavalink sunucusuna bağlanılamadı: {e}")


bot = Bot()


# ---------- Müzik olayları ----------
@bot.event
async def on_wavelink_node_ready(payload: wavelink.NodeReadyEventPayload):
    print(f"Lavalink bağlandı: {payload.node.identifier}")


@bot.event
async def on_wavelink_track_start(payload: wavelink.TrackStartEventPayload):
    print(f"Çalınıyor: {payload.track.title}")


@bot.event
async def on_wavelink_track_exception(payload: wavelink.TrackExceptionEventPayload):
    print(f"Şarkı hatası: {payload.track.title} -> {payload.exception}")


# ---------- Komutlar ----------
@bot.tree.command(name="sosyal", description="Sosyal medya linklerini gönderir")
async def sosyal(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    embed, file = build_message()
    if file:
        await interaction.channel.send(embed=embed, file=file)
    else:
        await interaction.channel.send(embed=embed)
    await interaction.delete_original_response()


@bot.tree.command(name="cal", description="Şarkı çalar (şarkı adı veya link)")
@app_commands.describe(sarki="Şarkı adı veya link")
async def cal(interaction: discord.Interaction, sarki: str):
    voice = interaction.user.voice
    if not voice or not voice.channel:
        await interaction.response.send_message(
            "Önce bir ses kanalına gir.", ephemeral=True
        )
        return

    await interaction.response.defer()

    vc: wavelink.Player = interaction.guild.voice_client
    if not vc:
        vc = await voice.channel.connect(cls=wavelink.Player, self_deaf=True)
        vc.autoplay = wavelink.AutoPlayMode.partial  # sırayı otomatik oynatır
    elif vc.channel != voice.channel:
        await vc.move_to(voice.channel)

    try:
        tracks = await wavelink.Playable.search(
            sarki, source=wavelink.TrackSource.SoundCloud
        )
    except Exception as e:
        print(f"Arama hatası: {e}")
        await interaction.followup.send("Arama sırasında bir hata oldu.")
        return

    if not tracks:
        await interaction.followup.send("Şarkı bulunamadı.")
        return

    if isinstance(tracks, wavelink.Playlist):
        added = await vc.queue.put_wait(tracks)
        title = f"{tracks.name} ({added} şarkı)"
    else:
        track = tracks[0]
        await vc.queue.put_wait(track)
        title = track.title

    if not vc.playing:
        await vc.play(vc.queue.get())
        await interaction.followup.send(f"Çalıyor: **{title}**")
    else:
        await interaction.followup.send(f"Sıraya eklendi: **{title}**")


@bot.tree.command(name="atla", description="Şarkıyı atlar")
async def atla(interaction: discord.Interaction):
    vc: wavelink.Player = interaction.guild.voice_client
    if vc and vc.playing:
        await vc.skip(force=True)
        await interaction.response.send_message("Şarkı atlandı.")
    else:
        await interaction.response.send_message("Şu an şarkı çalmıyor.", ephemeral=True)


@bot.tree.command(name="duraklat", description="Şarkıyı duraklatır")
async def duraklat(interaction: discord.Interaction):
    vc: wavelink.Player = interaction.guild.voice_client
    if vc and vc.playing and not vc.paused:
        await vc.pause(True)
        await interaction.response.send_message("Duraklatıldı.")
    else:
        await interaction.response.send_message("Şu an şarkı çalmıyor.", ephemeral=True)


@bot.tree.command(name="devam", description="Duraklatılan şarkıya devam eder")
async def devam(interaction: discord.Interaction):
    vc: wavelink.Player = interaction.guild.voice_client
    if vc and vc.paused:
        await vc.pause(False)
        await interaction.response.send_message("Devam ediyor.")
    else:
        await interaction.response.send_message("Duraklatılmış şarkı yok.", ephemeral=True)


@bot.tree.command(name="kuyruk", description="Şarkı sırasını gösterir")
async def kuyruk(interaction: discord.Interaction):
    vc: wavelink.Player = interaction.guild.voice_client
    if not vc or not vc.queue:
        await interaction.response.send_message("Sıra boş.", ephemeral=True)
        return
    lines = [f"{i}. {t.title}" for i, t in enumerate(list(vc.queue)[:10], start=1)]
    await interaction.response.send_message("**Sıradakiler:**\n" + "\n".join(lines))


@bot.tree.command(name="dur", description="Müziği durdurur ve sesten çıkar")
async def dur(interaction: discord.Interaction):
    vc: wavelink.Player = interaction.guild.voice_client
    if not vc:
        await interaction.response.send_message("Zaten ses kanalında değilim.", ephemeral=True)
        return
    vc.queue.clear()
    await vc.disconnect()
    await interaction.response.send_message("Durduruldu, kanaldan çıktım.")


@bot.event
async def on_ready():
    print(f"Giriş yapıldı: {bot.user}")


bot.run(TOKEN)