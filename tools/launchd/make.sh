#!/bin/bash
# Writes one launchd daemon per job into this folder: com.wbmstudio.newweb-<job>.plist.
# Each starts at boot, runs as mark, and is restarted 30 s after it stops for any reason.
# extdrive-exec comes first: it holds the Full Disk Access grant that lets daemons read /Volumes/4tb-ext.
cd "$(dirname "$0")"
for j in hn bluesky gharchive hf aicommits mastodon devto galleries labs liveness spn listing shots; do
cat > com.wbmstudio.newweb-$j.plist <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.wbmstudio.newweb-$j</string>
  <key>UserName</key><string>mark</string>
  <key>ProgramArguments</key><array>
    <string>/usr/local/libexec/extdrive-exec</string>
    <string>/Users/mark/newweb/venv/bin/python</string><string>-m</string><string>newweb.$j</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/mark/newweb</string>
  <key>EnvironmentVariables</key><dict>
    <key>HOME</key><string>/Users/mark</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>PYTHONUNBUFFERED</key><string>1</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>/Users/mark/newweb/logs/$j.log</string>
  <key>StandardErrorPath</key><string>/Users/mark/newweb/logs/$j.log</string>
</dict></plist>
PLIST
done
