# SPDX-License-Identifier: GPL-2.0-only
include $(TOPDIR)/rules.mk
PKG_NAME:=xr1710g-ft-proxy
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only
include $(INCLUDE_DIR)/package.mk
define Package/xr1710g-ft-proxy
	SECTION:=net
	CATEGORY:=Network
	TITLE:=Owned XR1710G FT endpoint Mesh proxy refresh
	DEPENDS:=+uci +iw +xr1710g-ap-configurator
endef
define Build/Prepare
	$(call Build/Prepare/Default)
	$(CP) ./src/* $(PKG_BUILD_DIR)/
endef
define Build/Compile
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_CPPFLAGS) -Wall -Wextra -Werror $(PKG_BUILD_DIR)/proxy.c $(TARGET_LDFLAGS) -o $(PKG_BUILD_DIR)/xr1710g-ft-proxy-send
endef
define Package/xr1710g-ft-proxy/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/etc/init.d
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/xr1710g-ft-proxy-send $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/xr1710g-ft-proxy-loop $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/xr1710g_ft_proxy $(1)/etc/init.d/
endef
$(eval $(call BuildPackage,xr1710g-ft-proxy))
