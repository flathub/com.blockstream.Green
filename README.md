# Blockstream

This repo hosts the flatpak version of [Blockstream](https://github.com/blockstream/green_qt).

Blockstream is an industry-leading Bitcoin wallet that offers you an unrivaled blend of security and ease-of-use.

## Manual Install and Run

Make sure you follow the [setup guide for your Linux distribution](https://flathub.org/en/setup) before installing.

```bash
flatpak install flathub com.blockstream.Green
flatpak run com.blockstream.Green
```

## Building

```bash
git clone git@github.com:flathub/com.blockstream.Green.git
flatpak run org.flatpak.Builder build-dir --user --ccache --force-clean --install com.blockstream.Green.yml
```

## Issue Reporting

**Please only report issues in this repo that are specific to the flatpak version.**

Issues that can be replicated in a stable release should be reported in the [upstream repo](https://github.com/blockstream/green_qt).
Make sure that the reported issue is **not** flatpak-related.
