obj-m += xr_npu_addresses.o
ifeq ($(XR_DIAG_VM_FIXTURE),1)
ccflags-y += -DXR_DIAG_VM_FIXTURE
obj-m += xr_npu_fixture.o
endif
