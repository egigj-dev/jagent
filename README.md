<!-- Jagent deployment instructions; unit names identify the daily pipeline, schedule and dashboard. -->
# jagent

## Using the dashboard

Open <http://127.0.0.1:8000/>. Start with **Profile** to enter your background,
skills, career goals, and preferred countries or remote regions. Plain text is
accepted; optional `## Section` headings organize separate areas of experience.
Changed profile text is matched during the next daily pipeline run. Saved jobs
and application records remain available across profile versions.

**Opportunities** shows your shortlist. Search by job title, company, or location;
filter by website, experience level, employment type, remote status, or saved
jobs. Sort by profile match, newest posting, deadline, company, or job title.
Filters stay selected when reviewing jobs. **Preferences** changes the underlying
location and excluded-title rules; view filters only narrow the current shortlist.
Apply through the original job website, then use **Mark as applied** to record it.

## Daily schedule

The pipeline runs at 07:00 Europe/Tirane, with missed runs caught up after reboot.
It runs `jagent run`, `jagent match`, `jagent analyze`, then `jagent health`,
continuing after failures and returning exit code 1 if any step fails. Logs use UTC.
The dashboard runs continuously at <http://127.0.0.1:8000/>.
Refresh `imports/duapune.json` from the laptop regularly: imports older than 36 hours
are reported by health and the dashboard banner.

Install the units:

```bash
sudo install -m 644 /home/egigj/jagent/deploy/jagent.service /etc/systemd/system/jagent.service
sudo install -m 644 /home/egigj/jagent/deploy/jagent.timer /etc/systemd/system/jagent.timer
sudo install -m 644 /home/egigj/jagent/deploy/jagent-web.service /etc/systemd/system/jagent-web.service
sudo systemctl daemon-reload
```

Enable the daily service at boot, start the timer, and start the dashboard:

```bash
sudo systemctl enable jagent.service
sudo systemctl enable --now jagent.timer
sudo systemctl enable --now jagent-web.service
```

Check both services, the next scheduled run, and logs. The oneshot daily service
is normally inactive between runs; its last result appears in its status and logs.

```bash
sudo systemctl status jagent.service jagent-web.service jagent.timer --no-pager
sudo systemctl list-timers jagent.timer --all --no-pager
sudo journalctl -u jagent.service -n 100 --no-pager
sudo journalctl -u jagent-web.service -n 100 --no-pager
```

To run the installed pipeline immediately:

```bash
sudo systemctl start jagent.service
```
