obj-m += xr_npu_runtime.o
ifeq ($(XR_DIAG_VM_FIXTURE),1)
ccflags-y += -DXR_DIAG_VM_FIXTURE
obj-m += xr_npu_runtime_fixture.o
endif
