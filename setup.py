from distutils.core import setup
setup(
    name='Django easyapi',
    packages=['easyapi'],
    version='0.0.1',
    license='MIT',
    description='A simple rest api generator for django based on models',
    author='Stamatios Stamou Jr',
    author_email='ssjunior-pypy@gmail.com',
    url='https://github.com/ssjunior/django-easyapi',
    download_url='https://github.com/ssjunior/django-easyapi/archive/refs/tags/v0.0.1.tar.gz',    # I explain this later on
    keywords=['Django', 'Rest', 'Api'],
    install_requires=[
        'Django>=4.1.3',
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.7',
    ],
)
