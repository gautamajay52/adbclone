# ⚡adbclone [![Hits](https://hits.seeyoufarm.com/api/count/incr/badge.svg?url=https%3A%2F%2Fgithub.com%2Fgautamajay52%2Fadbclone&count_bg=%2379C83D&title_bg=%23555555&icon=&icon_color=%23E7E7E7&title=hits&edge_flat=false)](https://github.com/gautamajay52/adbclone)

> A [rclone](https://rclone.org/) like program to copy files between a computer and an Android device

## ⚡Installation:

Available on [PyPI](https://pypi.org/project/adbclone/)

```
pip install adbclone
```

## ⚡Usage:

To push from your computer to your phone use

```
adbclone push LOCAL ANDROID
```

To pull from your phone to your computer use

```
adbclone pull ANDROID LOCAL
```

Full help is available with `$ adbclone --help`

## ⚡Flags:
- `--show-tree` Show tree of source and destination
- `--del` will delete files and folders on the destination end that are not present on the source end. This does not include exluded files.
- `--delete-excluded` will delete excluded files and folders on the destination end.
- `--exclude` can be used many times. Each should be a `fnmatch` pattern relative to the source. These patterns will be ignored unless `--delete-excluded` is specified.
- `--exclude-from` can be used many times. Each should be a filename of a file containing `fnmatch` patterns relative to the source.

## ⚡ToDos:
- [x] Add Progress
- [ ] Multiple Transfers
- [ ] Add more ToDos

# ⚡Demo:
![adbclone GIF](https://raw.githubusercontent.com/gautamajay52/filestore/main/adbclone.gif)

## ⚡Credits:
* [GautamKumar(me)](https://github.com/gautamajay52) for [Something](https://github.com/gautamajay52/adbclone)
* [adb-sync](https://github.com/jb2170/better-adb-sync) for all the hard-work.

#
<details>

<summary> <strong> Previous Readme </strong></summary>

# Better ADB Sync

An [rsync](https://wiki.archlinux.org/title/rsync)-like program to sync files between a computer and an Android device

## Installation

Available on [PyPI](https://pypi.org/project/BetterADBSync/)

```
$ pip install BetterADBSync
```

## QRD

To push from your computer to your phone use
```
$ adbsync push LOCAL ANDROID
```

To pull from your phone to your computer use
```
$ adbsync pull ANDROID LOCAL
```

Full help is available with `$ adbsync --help`

## Intro

This is a (pretty much from scratch) rewrite of Google's [adbsync](https://github.com/google/adb-sync) repo.

The reason for the rewrite is to

1. Update the repo to Python 3 codestyle (strings are by default UTF-8, no more b"" and u"", classes don't need to inherit from object, 4 space indentation etc)
2. Add in support for `--exclude`, `--exclude-from`, `--del`, `--delete-excluded` like `rsync` has (this required a complete rewrite of the diffing algorithm)

## Additions

- `--del` will delete files and folders on the destination end that are not present on the source end. This does not include exluded files.
- `--delete-excluded` will delete excluded files and folders on the destination end.
- `--exclude` can be used many times. Each should be a `fnmatch` pattern relative to the source. These patterns will be ignored unless `--delete-excluded` is specified.
- `--exclude-from` can be used many times. Each should be a filename of a file containing `fnmatch` patterns relative to the source.

## Possible future TODOs

I am satisfied with my code so far, however a few things could be added if they are ever needed

- `--backup` and `--backup-dir-local` or `--backup-dir-android` to move outdated / to-delete files to another folder instead of deleting

---

---BEGIN ORIGINAL README.md---

adb-sync
========

adb-sync is a tool to synchronize files between a PC and an Android device
using the ADB (Android Debug Bridge).

Related Projects
================

Before getting used to this, please review this list of projects that are
somehow related to adb-sync and may fulfill your needs better:

* [rsync](http://rsync.samba.org/) is a file synchronization tool for local
  (including FUSE) file systems or SSH connections. This can be used even with
  Android devices if rooted or using an app like
  [SSHelper](https://play.google.com/store/apps/details?id=com.arachnoid.sshelper).
* [adbfs](http://collectskin.com/adbfs/) is a FUSE file system that uses adb to
  communicate to the device. Requires a rooted device, though.
* [adbfs-rootless](https://github.com/spion/adbfs-rootless) is a fork of adbfs
  that requires no root on the device. Does not play very well with rsync.
* [go-mtpfs](https://github.com/hanwen/go-mtpfs) is a FUSE file system to
  connect to Android devices via MTP. Due to MTP's restrictions, only a certain
  set of file extensions is supported. To store unsupported files, just add
  .txt! Requires no USB debugging mode.

Setup
=====

Android Side
------------

First you need to enable USB debugging mode. This allows authorized computers
(on Android before 4.4.3 all computers) to perform possibly dangerous
operations on your device. If you do not accept this risk, do not proceed and
try using [go-mtpfs](https://github.com/hanwen/go-mtpfs) instead!

On your Android device:

* Go to the Settings app.
* If there is no "Developer Options" menu:
  * Select "About".
  * Tap "Build Number" seven times.
  * Go back.
* Go to "Developer Options".
* Enable "USB Debugging".

PC Side
-------

* Install the [Android SDK](http://developer.android.com/sdk/index.html) (the
  stand-alone Android SDK "for an existing IDE" is sufficient). Alternatively,
  some Linux distributions come with a package named like "android-tools-adb"
  that contains the required tool.
* Make sure "adb" is in your PATH. If you use a package from your Linux
  distribution, this should already be the case; if you used the SDK, you
  probably will have to add an entry to PATH in your ~/.profile file, log out
  and log back in.
* `git clone https://github.com/google/adb-sync`
* `cd adb-sync`
* Copy or symlink the adb-sync script somewhere in your PATH. For example:
  `cp adb-sync /usr/local/bin/`

Usage
=====

To get a full help, type:

```
adb-sync --help
```

To synchronize your music files from ~/Music to your device, type one of:

```
adb-sync ~/Music /sdcard
adb-sync ~/Music/ /sdcard/Music
```

To synchronize your music files from ~/Music to your device, deleting files you
removed from your PC, type one of:

```
adb-sync --delete ~/Music /sdcard
adb-sync --delete ~/Music/ /sdcard/Music
```

To copy all downloads from your device to your PC, type:

```
adb-sync --reverse /sdcard/Download/ ~/Downloads
```

ADB Channel
===========

This package also contains a separate tool called adb-channel, which is a
convenience wrapper to connect a networking socket on the Android device to
file descriptors on the PC side. It can even launch and shut down the given
application automatically!

It is best used as a `ProxyCommand` for SSH (install
[SSHelper](https://play.google.com/store/apps/details?id=com.arachnoid.sshelper)
first) using a configuration like:

```
Host sshelper
Port 2222
ProxyCommand adb-channel tcp:%p com.arachnoid.sshelper/.SSHelperActivity 1
```

After adding this to `~/.ssh/config`, run `ssh-copy-id sshelper`.

Congratulations! You can now use `rsync`, `sshfs` etc. to the host name
`sshelper`.

Contributing
============

Patches to this project are very welcome.

Before sending a patch or pull request, we ask you to fill out one of the
Contributor License Agreements:

* [Google Individual Contributor License Agreement, v1.1](https://developers.google.com/open-source/cla/individual)
* [Google Software Grant and Corporate Contributor License Agreement, v1.1](https://developers.google.com/open-source/cla/corporate)

Disclaimer
==========

This is not an official Google product.


---END ORIGINAL README.md---

---
</details>