import versioneer
from setuptools import setup, find_packages

with open('requirements.txt') as f:
    requirements = f.read().split()

git_requirements = [r for r in requirements if r.startswith('git+')]
requirements = [r for r in requirements if not r.startswith('git+')]

if len(git_requirements) > 0:
    print("User must install \n" +
          "\n".join(f' {r}' for r in git_requirements) +
          "\n\nmanually")

setup(name='pydm_pva_widgets',
      author='SLAC National Accelerator Laboratory',
      version=versioneer.get_version(),
      cmdclass=versioneer.get_cmdclass(),
      packages=find_packages(),
      include_package_data=True,
      install_requires=requirements,
      description='PyDM PVA Widget Library',
      )
