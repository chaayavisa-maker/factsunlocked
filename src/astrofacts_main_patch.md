## Patch instructions for src/astrofacts_main.py

The original astrofacts_main.py structure is correct and should be kept.
Apply these two targeted changes:

### Change 1: Multi-playlist support in publish_sign()
Replace the single playlist_id lookup:
    playlist_id = YT_CFG.get("playlist_ids", {}).get(period)

With multi-playlist support:
    period_playlist = YT_CFG.get("playlist_ids", {}).get(period, "")
    sign_playlist   = YT_CFG.get("sign_playlist_ids", {}).get(sign, "")
    playlist_ids    = [p for p in [period_playlist, sign_playlist] if p and p.strip()]
    playlist_id     = playlist_ids if playlist_ids else None

Then pass playlist_id (now a list) to upload_video() — the improved youtube.py
already handles both str and list.

### Change 2: Pinned comment in publish_sign()
After the YouTube upload call, add pinned_comment= to upload_video():

    PINNED_COMMENTS = {
        "daily":   "Did this resonate? Drop a ⭐ below and tell me which part hit different!",
        "weekly":  "Which part of this week's reading are you most focused on? 👇",
        "monthly": "What's the ONE thing you're calling in this month? Share it below 🌙",
        "yearly":  "What's your biggest intention for this year? Drop it below ✨",
    }

    yt_id = upload_video(
        ...existing args...,
        playlist_id=playlist_id,
        pinned_comment=PINNED_COMMENTS.get(period, ""),
    )

No other changes needed — staggering is now fully handled by the 4 cron workflows.
