%define __brp_python_bytecompile %{nil}
Name:       harbour-sailfish-lls-remote
Summary:    LLs vPlayer MPRIS sidecar for LAN control
Version:    0.1.1
Release:    1
Group:      Applications/Multimedia
License:    MIT
Source0:    %{name}-%{version}.tar.bz2
BuildArch:  noarch
Requires:   /usr/bin/python3
Requires:   /usr/bin/gdbus

%description
Phone-side HTTP sidecar that exposes LLs vPlayer control and status over the
local network on port 8091 by forwarding requests to the player's MPRIS D-Bus
interface.

%prep
%setup -q -n %{name}-%{version}

%build

%install
rm -rf %{buildroot}
install -Dpm755 harbour-sailfish-lls-remote %{buildroot}%{_bindir}/harbour-sailfish-lls-remote
install -Dpm644 remote_control.py %{buildroot}%{_datadir}/harbour-sailfish-lls-remote/remote_control.py
install -Dpm644 mpris_adapter.py %{buildroot}%{_datadir}/harbour-sailfish-lls-remote/mpris_adapter.py
install -Dpm644 harbour-sailfish-lls-remote.service %{buildroot}/usr/lib/systemd/user/harbour-sailfish-lls-remote.service

%files
%defattr(-,root,root,-)
%{_bindir}/harbour-sailfish-lls-remote
%{_datadir}/harbour-sailfish-lls-remote/remote_control.py
%{_datadir}/harbour-sailfish-lls-remote/mpris_adapter.py
/usr/lib/systemd/user/harbour-sailfish-lls-remote.service
