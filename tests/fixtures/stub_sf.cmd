@echo off
rem Stand-in for the sf CLI used by tests/backend/test_orglogin.py. AVIO_TEST_PYTHON is set by the test.
if "%AVIO_TEST_PYTHON%"=="" (python "%~dp0stub_sf.py" %*) else ("%AVIO_TEST_PYTHON%" "%~dp0stub_sf.py" %*)
