### set version number

Use a version that conforms to semantic versioning 2.0.

Update the `NEWS.md` file and (usually) all `setup.py` files.
Note the versioning scheme remark in the toplevel `setup.py` file.

#### Version number
Originally fody-backend had been designed with sub-modules
that could potentially also be used separately.
Example how to change all version numbers:
```sh
grep -r "^    version=" .
grep -rl "^    version=" . | xargs sed -i 's/0.4.4.dev0/0.5.0.dev0/'
```

#### DEB packaging
You need to add an new entry to `debian/changelog` for releases.
```sh
dch --newversion 0.7.0  --check-dirname-level 0 --distribution stable
```

When the version of fody compatible with the backend changed, also
update the dependency in `debian/control`.

### Tag version
example
```sh
git tag -s v0.7.0
git push origin v0.7.0
```

### build
(whatever is necessary, see toplevel Readme)

### Prepare for following development
In the mentioned files above, set the version number to the following
number as pre-version number for development, e.g. `0.7.1.dev0`.
