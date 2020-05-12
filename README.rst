****************************
Mopidy-Plex
****************************

Mopidy extension for playing audio from a Plex server

Installation
============

Install from source from this repo, the package index repo is unmaintained:

    git clone https://github.com/sbaier1/mopidy_plex.git
    python3 -m pip install .

Configuration
=============

Before starting Mopidy, you must add configuration for
Mopidy-Plex to your Mopidy configuration file::

    [plex]
    type = myplex
    enabled = true
    server = Servername
    username = Username
    password = Password
    library = Music

Servername above is the name of the server (not the hostname and port). If logged into Plex Web you can see the server name in the top left above your available libraries.

You can also use direct as type to connect directly to your server instead of authenticating through MyPlex if your server is unclaimed (not logged in)

Troubleshooting
===============

If you are having trouble with some library items, you must change the default encoding in your mopidy startup script::

    if __name__ == '__main__':
        reload(sys)
        sys.setdefaultencoding('UTF8')
        sys.exit(
            load_entry_point('Mopidy==3.0.0a1', 'console_scripts', 'mopidy')()
        )

Project resources
=================

- `Source code <https://github.com/sbaier1/mopidy-plex>`_
- `Issue tracker <https://github.com/sbaier1/mopidy-plex/issues>`_


Credits
=======

- Original author: `@havardgulldahl <https://github.com/havardgulldahl>`_
- Current maintainer: `@sbaier1 <https://github.com/sbaier1>`_
- `Contributors <https://github.com/sbaier1/mopidy-plex/graphs/contributors>`_


Changelog
=========

v0.1.0 (UNRELEASED)
----------------------------------------


v0.1.0b (2016-02-02)
----------------------------------------

- Initial beta release.
- Listing and searching Plex Server content works.
- Playing audio works.
- Please `file bugs <https://github.com/havardgulldahl/mopidy-plex/issues>`_.


v0.1.0c (2016-06-29)
----------------------------------------

- Add support for remote Plex Servers

v3.0.0 (2020-05-12)
----------------------------------------

- Update plexapi support to latest version
- Add support for MyPlex backend from plexapi to connect to servers through official authN API
- Add support for playlists in library
- Add mopidy3 / python3 support
- Add caching for image thumbnails