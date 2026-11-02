#!/bin/sh
# firewall.sh <demo.env> (root): the demo's port answers the front proxy (DEMO_PROXY_IP) only, and no container
# of the demo starts a connection to the LAN, the internet or the host itself. Idempotent: the watchdog runs it
# every minute.
# Docker's published ports bypass ufw; DOCKER-USER is the chain Docker leaves to us.
set -eu
case $1 in */*) . "$1" ;; *) . "./$1" ;; esac
iptables -N DEMO-EDGE 2>/dev/null || true
iptables -F DEMO-EDGE
iptables -A DEMO-EDGE -s "$DEMO_PROXY_IP" -j RETURN
iptables -A DEMO-EDGE -j DROP
rule="-p tcp -m conntrack --ctdir ORIGINAL --ctorigdst $DEMO_BIND --ctorigdstport ${DEMO_PORT:-8780} -j DEMO-EDGE"
iptables -C DOCKER-USER $rule 2>/dev/null || iptables -I DOCKER-USER $rule
# the demo's bridges start nothing: no new connection out of the edge, none to the host's own addresses (INPUT)
for n in demo-pub demo-int; do
    id=$(docker network inspect -f '{{.Id}}' "yashome-demo_$n" 2>/dev/null | cut -c1-12)
    [ -n "$id" ] || continue
    iptables -D DOCKER-USER -i "br-$id" -m conntrack --ctstate NEW -j DROP 2>/dev/null || true      # an older form of the rule
    out="-i br-$id ! -o br-$id -m conntrack --ctstate NEW -j DROP"        # containers of one network still talk
    iptables -C DOCKER-USER $out 2>/dev/null || iptables -I DOCKER-USER $out
    host="-i br-$id -m conntrack --ctstate NEW -j DROP"
    iptables -C INPUT $host 2>/dev/null || iptables -I INPUT $host
done
