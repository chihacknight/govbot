# Home runner: a Linux laptop for the scrapers

Brief for the chat that sets this up. Written 2026-11-25 by the reviewing chat.

> **The goal:** turn an old MacBook Pro into an always-on GitHub Actions runner at Tamara's
> home, for the scrapes that can't run on GitHub's servers. This chat sets up the machine and
> proves it works. It doesn't change which states run where. That's a later decision for Tamara
> (see "Open decisions").

## Ground rules

- **The scrapers stay paused.** There's no pressure to unpause. Don't unpause a state, and don't
  change `chn-openstates-scrape.yml` routing, without Tamara's OK.
- **A test scrape commits to that state's raw repo** (`govbot-openstates-scrapers/<st>-legislation`).
  Tamara picks the state and the time before any run is started.
- Commit or push only when Tamara says so. The repo squash-merges: after a PR merges, start a
  fresh branch off `main`.
- Tamara's main laptop is short on disk. Anything big goes on the SSD,
  `/Volumes/govbot-data/scratch/`.

## Why a home machine

GitHub's servers can't do everything:

- **Blocked addresses.** Some state sites block or degrade data-centre addresses. PA is a
  confirmed address-reputation block (`tamara-notes/state-specific/pa.md`).
- **The 6-hour limit.** A job on GitHub's servers is killed at 6 hours, whatever `timeout-minutes`
  says. FL and MA scrapes run longer.
- **The old home runner was a Mac laptop ("MacBookPro"),** which had to be on and connected. FL and
  MA runs were cancelled after waiting 24 hours for it
  (`tamara-notes/processes/handoff-2026-11-24.md`).

## How runs reach a home runner today

Read the comments in `actions/pipeline-manager/templates/openstates-scrape/.github/workflows/openstates-scrape.yml`
before assuming which runs land on the laptop. In short:

- `runs-on` asks only for the label **`self-hosted`**. Any operating system works, because the
  scrape itself runs inside the OpenStates Docker image.
- About 33 locales have `runner: self-hosted` in `actions/pipeline-manager/chn-openstates-scrape.yml`.
  **Their scheduled runs don't use the home runner.** They run on GitHub's servers through
  **tinyproxy**, a proxy on a GCP virtual machine.
- Only locales with **`force_self_hosted: true` (FL, MA)** send scheduled runs to the home runner.
- Any self-hosted locale can be sent there by hand: run the workflow manually with
  **`use-self-hosted`** ticked.
- So once the laptop is registered, it gets FL's and MA's scheduled runs (when unpaused) and any
  manual runs. Nothing else changes.

## The machine

- **13-inch Retina MacBook Pro, late 2012:** Intel dual-core, 8 GB RAM. Intel with no T2 chip, so
  standard Ubuntu installs normally. 8 GB is enough: a runner takes one job at a time.
- **No ethernet port.** Use Apple's Thunderbolt-to-Gigabit-Ethernet adapter, for the install and for
  running.
- **The Wi-Fi chip is Broadcom,** and needs `bcmwl-kernel-source` if Wi-Fi is wanted.
- **Old battery.** One left charging all the time can swell. Check that the case sits flat and the
  trackpad clicks normally. If not, have the battery removed or replaced first.
- **It was Tamara's ex's laptop, and the macOS password is forgotten.** That doesn't matter: the
  installer erases the disk, and the Option-key boot menu doesn't ask for it. Before wiping:
  1. Tamara checks with her ex that wiping is fine.
  2. Her ex removes the Mac from **Find My** on their Apple ID. Even 2012 Macs can be locked
     remotely with a PIN.
  3. A **padlock with a password box** at the Option-key menu means a firmware password (not the
     login one). The ex may know it; otherwise Apple removes it with proof of purchase.
- **Don't reinstall macOS.** The newest this model can run is Catalina, which has had no security
  updates since 2022 and isn't supported by current Docker Desktop.

## Setup steps

1. **Installer:** on another Mac, download **Ubuntu Server 24.04 LTS** and write it to a USB stick
   with balenaEtcher. Use Server, because the desktop uses memory the scrapes need. **Use 24.04, not 26.04:** see
   "Python" below.
2. **Install:**
   - Boot holding **Option** and choose "EFI Boot".
   - Erase the whole disk.
   - Tick **Install OpenSSH server**.
   - **Don't** tick Docker on the extra-software screen. That's the snap version.
3. **Always on:**
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y mbpfan            # Mac fan control
   sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
   sudoedit /etc/systemd/logind.conf     # HandleLidSwitch=ignore, HandleLidSwitchExternalPower=ignore
   sudo reboot
   ```
   Also set the machine to restart after a power cut, and check it still answers over SSH after a
   reboot with the lid closed.
4. **Docker Engine:** follow "Install using the apt repository" at
   docs.docker.com/engine/install/ubuntu. Then run `sudo usermod -aG docker $USER`, log out and
   back in, and check with `docker run hello-world`. Pull the scraper image once, to check disk
   space and download speed.
5. **Register the runner.** Tamara does this; she has the admin rights.
   - On GitHub: the `govbot-openstates-scrapers` org → Settings → Actions → Runners → New
     self-hosted runner → Linux, x64.
   - Run the commands it shows. The default labels include `self-hosted`.
   - Install it as a service, so it starts on boot: `sudo ./svc.sh install && sudo ./svc.sh start`.
   - **Runner group:** limit it to the `govbot-openstates-scrapers` repos. These repos are public,
     and a runner runs whatever their workflows say.
   - Keep nothing personal on this machine.
6. **The old "MacBookPro" runner:** check its status on the same page. If it's offline or retired,
   remove it, so that jobs don't queue for a machine that's gone. That's Tamara's call.
7. **Test run, when Tamara picks the state and time:**
   - Run one state's workflow manually with `use-self-hosted` ticked.
   - Watch it land on the new runner, then pass "Setup Python", the Docker scrape and the commit.
   - Compare its bill count with that state's last good scrape.
   - Record the result here.

## Python: a known failure, separate from this machine

- Since 2026-10-30, every scrape has failed at **"Setup Python"**. GitHub's `ubuntu-latest` moved to
  Ubuntu 26.04, and `setup-python` only installs GitHub's prebuilt copies of Python. There's no
  Python 3.9 build for 26.04. (3.9 itself installs fine on 26.04 in other ways.)
- `actions/scrape/action.yml` still asks for 3.9. A self-hosted 26.04 machine would fail the same
  way, hence 24.04.
- **The fix belongs to the scraper-fixes chat, not this one.** It's noted here so the two don't
  collide:
  - `actions/scrape` seems to use no Python outside Docker, so its "Setup Python" step can
    probably just be deleted. Check that first.
  - `actions/format` and `actions/extract` do use it: move them to 3.11, with `extract/Pipfile`.
  - Re-enable `extract-text.yml` in the 9 data repos where it was disabled on 2026-11-24.
- **Before relying on that,** pull one failed run's log and confirm that Setup Python is the only
  failure.
- That fix brings back the scrapes on GitHub's servers. It doesn't replace this laptop, which is for
  the blocked and too-long scrapes.

## Open decisions (Tamara's)

- Which state to test first, and when.
- Whether to keep or remove the old "MacBookPro" runner.
- **Later:** with a reliable home runner, should more states send their scheduled runs to it
  instead of tinyproxy? If so, which (PA first?), via `force_self_hosted` in
  `chn-openstates-scrape.yml`. That's a separate PR, after the scrapers unpause.

## Progress

(The setup chat adds dated entries here.)
