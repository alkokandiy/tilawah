# Tilawah APT repository
served via GitHub Pages from this branch.

```bash
echo "deb [trusted=yes] https://alkokandiy.github.io/tilawah/ ./" \
  | sudo tee /etc/apt/sources.list.d/tilawah.list
sudo apt update && sudo apt install tilawah
```
