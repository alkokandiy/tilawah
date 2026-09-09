test:
	python3 -m unittest discover -s tests -v

install:
	pip install .

deb:
	sh packaging/build-deb.sh

apt-repo:
	sh packaging/publish-apt.sh

clean:
	rm -rf build dist *.egg-info
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null; true
